import unittest
from menu import TEMPLATES, make_prompt, keyboard, banner_png

class MenuTests(unittest.TestCase):
    def test_ids_and_callback_limits(self):
        self.assertEqual(len({t['id'] for t in TEMPLATES}),len(TEMPLATES))
        for row in keyboard()['inline_keyboard']:
            for button in row:
                self.assertLessEqual(len(button['callback_data'].encode()),64)
    def test_name_required(self):
        for t in TEMPLATES:
            if t['id']!='devices':
                with self.assertRaises(ValueError): make_prompt(t['id'])
        self.assertIn('Geräte',make_prompt('devices'))
    def test_name_quoted(self):
        self.assertIn('"Wohnzimmer Sensor"',make_prompt('status','Wohnzimmer Sensor'))
        with self.assertRaises(ValueError): make_prompt('status','x'*201)
        with self.assertRaises(ValueError): make_prompt('status','a\nb')
        with self.assertRaises(ValueError): make_prompt('invalid','a')
    def test_banner(self):
        data=banner_png()
        self.assertTrue(data.startswith(b'\x89PNG\r\n\x1a\n'))
        self.assertGreater(len(data),100)

if __name__=='__main__': unittest.main()
