import io
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from PIL import Image

from accounts.models import User
from polls.models import Option, Poll
from polls.storage import ImageError, process_image

from .test_polls import PASSWORD

STORAGE = {"SUPABASE_URL": "https://proj.supabase.co", "SUPABASE_SERVICE_ROLE_KEY": "sb_secret_test"}
PUBLIC = "https://proj.supabase.co/storage/v1/object/public/option-images/"


def image_file(name="foto.png", size=(1600, 900), fmt="PNG"):
    buffer = io.BytesIO()
    Image.new("RGB", size, (124, 58, 237)).save(buffer, fmt)
    return SimpleUploadedFile(name, buffer.getvalue(), content_type=f"image/{fmt.lower()}")


class ProcessImageTests(TestCase):
    def test_resizes_to_webp(self):
        data = process_image(image_file())
        out = Image.open(io.BytesIO(data))
        self.assertEqual(out.format, "WEBP")
        self.assertEqual(max(out.size), 800)

    def test_rejects_non_images_and_big_files(self):
        with self.assertRaisesMessage(ImageError, "geçerli bir görsel değil"):
            process_image(SimpleUploadedFile("x.png", b"not an image"))
        big = SimpleUploadedFile("big.png", b"0" * (5 * 1024 * 1024 + 1))
        with self.assertRaisesMessage(ImageError, "5 MB"):
            process_image(big)


@override_settings(**STORAGE)
class UploadFlowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("ayse", "ayse@example.com", PASSWORD)
        self.client.force_login(self.user)

    def post(self, files, options=("Kedi", "Köpek")):
        data = {"question": "Hangi hayvanı sahiplensem?", "options": list(options), **files}
        return self.client.post(reverse("poll_create"), data)

    def test_form_shows_image_inputs_when_configured(self):
        self.assertContains(self.client.get(reverse("poll_create")), 'name="option_image_0"')

    @mock.patch("polls.storage._request", return_value=200)
    def test_upload_stores_public_url(self, request):
        self.post({"option_image_1": image_file()})
        kedi, kopek = Poll.objects.get().options.all()
        self.assertEqual(kedi.image_url, "")
        self.assertTrue(kopek.image_url.startswith(PUBLIC + "options/"))
        method, url = request.call_args[0][:2]
        self.assertEqual(method, "POST")
        self.assertEqual(request.call_args[1]["content_type"], "image/webp")
        page = self.client.get(Poll.objects.get().get_absolute_url())
        self.assertContains(page, kopek.image_url)

    @mock.patch("polls.storage._request", return_value=200)
    def test_image_on_blank_option_is_error(self, request):
        r = self.post({"option_image_2": image_file()}, options=("Kedi", "Köpek", ""))
        self.assertContains(r, "seçeneğe bir metin de yaz")
        self.assertFalse(Poll.objects.exists())
        request.assert_not_called()

    @mock.patch("polls.storage._request", return_value=200)
    def test_invalid_image_is_field_error(self, request):
        r = self.post({"option_image_0": SimpleUploadedFile("x.png", b"nope")})
        self.assertContains(r, "geçerli bir görsel değil")
        self.assertFalse(Poll.objects.exists())

    def test_upload_failure_keeps_form_and_creates_nothing(self):
        import urllib.error
        with mock.patch("polls.storage._request", side_effect=urllib.error.URLError("down")):
            r = self.post({"option_image_0": image_file()})
        self.assertContains(r, "Görsel yüklenemedi")
        self.assertFalse(Poll.objects.exists())

    @mock.patch("polls.storage._request", return_value=200)
    def test_delete_poll_removes_images(self, request):
        self.post({"option_image_0": image_file()})
        poll = Poll.objects.get()
        request.reset_mock()
        self.client.post(reverse("poll_delete", args=[poll.pk]))
        method, url = request.call_args[0][:2]
        self.assertEqual(method, "DELETE")
        self.assertIn(b"options/", request.call_args[1]["data"])

    @mock.patch("polls.storage._request", return_value=200)
    def test_vote_json_includes_image_url(self, request):
        self.post({"option_image_0": image_file()})
        poll = Poll.objects.get()
        c = Client(); c.get("/")
        data = c.post(reverse("poll_vote", args=[poll.pk]), {"option_id": poll.options.first().pk}, HTTP_ACCEPT="application/json").json()
        self.assertIn("image_url", data["results"][0])
        self.assertNotIn("image_url", data["results"][1])


class NoStorageTests(TestCase):
    def test_file_inputs_hidden_and_files_ignored(self):
        user = User.objects.create_user("ayse", "ayse@example.com", PASSWORD)
        self.client.force_login(user)
        self.assertNotContains(self.client.get(reverse("poll_create")), "option_image_0")
        self.client.post(reverse("poll_create"), {"question": "Görselsiz soru burada?", "options": ["A1", "B2"], "option_image_0": image_file()})
        self.assertFalse(Option.objects.exclude(image_url="").exists())
