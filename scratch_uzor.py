import fitz
import re

# We can render these exact sub-rectangles from the PDF using PyMuPDF to SVG or create clean SVG trees!
doc = fitz.open('frontend/brandbook/MGT_logos_2020/MGT_uzor.pdf')
page = doc[0]

# PyMuPDF lets us export SVG of a cropped page!
# 1. Blue pattern
page.set_cropbox(fitz.Rect(0.588, 75.216, 422.161, 149.015))
blue_svg = page.get_svg_image()
with open('frontend/public/mgt_uzor_blue.svg', 'w', encoding='utf-8') as f:
    f.write(blue_svg)

# 2. White pattern (on transparent background)
page.set_cropbox(fitz.Rect(0.588, 196.618, 422.161, 270.417))
# Note: In PDF, the white rings are on top of drawing 0 (the blue rectangle).
# If we crop here, does it include drawing 0?
# Let's check!
white_crop_svg = page.get_svg_image()
print("white_crop_svg length:", len(white_crop_svg))

# 3. Banner
page.set_cropbox(fitz.Rect(0.473, 185.965, 421.479, 280.234))
banner_svg = page.get_svg_image()
with open('frontend/public/mgt_uzor_banner.svg', 'w', encoding='utf-8') as f:
    f.write(banner_svg)

print("Saved preliminary cropped SVGs")
