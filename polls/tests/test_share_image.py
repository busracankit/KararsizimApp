import io

from django.test import TestCase
from django.urls import reverse
from PIL import Image

from accounts.models import User
from polls.models import Poll
from polls.share_image import clean

from .test_polls import PASSWORD, make_poll


class ShareImageTests(TestCase):
    def setUp(self):
        user = User.objects.create_user("ayse", "ayse@example.com", PASSWORD)
        self.poll = make_poll(user, "Bugün sinemaya mı gitsem, restorana mı? 🎬 Çok kararsızım, şğıİÖÇü", options=("Sinema 🎬", "Restoran", "Evde film + pizza", "Sahil", "Uyku"))

    def test_png_card(self):
        r = self.client.get(reverse("poll_share_image", args=[self.poll.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"], "image/png")
        self.assertIn("max-age", r["Cache-Control"])
        self.assertEqual(Image.open(io.BytesIO(r.content)).size, (1200, 630))

    def test_detail_links_og_image(self):
        r = self.client.get(self.poll.get_absolute_url())
        self.assertContains(r, f'<meta property="og:image" content="http://testserver/anket/{self.poll.pk}/paylasim.png">')
        self.assertContains(r, 'content="summary_large_image"')

    def test_hidden_poll_has_no_image(self):
        Poll.objects.filter(pk=self.poll.pk).update(is_hidden=True)
        self.assertEqual(self.client.get(reverse("poll_share_image", args=[self.poll.pk])).status_code, 404)

    def test_clean_drops_emoji_keeps_turkish(self):
        self.assertEqual(clean("Sinema 🎬 şğıİ"), "Sinema şğıİ")
