import xml.etree.ElementTree as ET

# Read mgt_uzor_full.svg
tree = ET.parse('frontend/public/mgt_uzor_full.svg')
root = tree.getroot()

# Let's inspect all <g> and <path> elements
# Total paths: 57
# Path 1 is the blue rectangle (fill="#007cba")
# Paths 2-18 are the blue wave elements (fill="#007cba")
# Paths 19-35 are the white wave elements (fill="#ffffff")

all_paths = root.findall('.//{http://www.w3.org/2000/svg}path')
print("Total paths:", len(all_paths))

# Notice that all paths have transform="matrix(1,0,0,-1, tx, ty)"
# In PyMuPDF SVG output:
# The root SVG has viewBox="0 0 421.479 337.483"
# y=0 is top, y=337.483 is bottom.
# For blue rings, the Y range in the PDF was 75.216 to 149.015.
# Let's verify what the rendered bounding box is in SVG coordinates!

# If we create an SVG with viewBox="0.5 75 421 74":
# The blue paths (2-18) will display in that viewBox!
# Let's test this!

def make_svg_from_paths(selected_paths, width, height, viewbox, bg_rect=None):
    svg_str = f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="{viewbox}">\n'
    if bg_rect:
        svg_str += f'  <rect x="{bg_rect[0]}" y="{bg_rect[1]}" width="{bg_rect[2]}" height="{bg_rect[3]}" fill="{bg_rect[4]}" />\n'
    for p in selected_paths:
        d = p.attrib.get('d', '')
        transform = p.attrib.get('transform', '')
        fill = p.attrib.get('fill', '#0076bc')
        tr_attr = f' transform="{transform}"' if transform else ''
        svg_str += f'  <path d="{d}" fill="{fill}"{tr_attr} />\n'
    svg_str += '</svg>\n'
    return svg_str

# 1. Blue rings: paths 2 to 18
# Bbox in PDF: x: 0.588 to 421.479, y: 75.216 to 149.015
# Width: 421.479 - 0.588 = 420.891, Height: 149.015 - 75.216 = 73.799
blue_paths = all_paths[2:19]
blue_svg = make_svg_from_paths(blue_paths, 422, 74, "0.588 75.216 421 73.8")
with open('frontend/public/mgt_uzor_blue.svg', 'w', encoding='utf-8') as f:
    f.write(blue_svg)

# 2. White rings: paths 19 to 36
# Bbox in PDF: x: 0.588 to 421.479, y: 196.618 to 270.417
# Width: 421, Height: 73.8
white_paths = all_paths[19:36]
white_svg = make_svg_from_paths(white_paths, 422, 74, "0.588 196.618 421 73.8")
with open('frontend/public/mgt_uzor_white.svg', 'w', encoding='utf-8') as f:
    f.write(white_svg)

# 3. Banner: blue rectangle background + white rings
# Banner rect in PDF: x: 0.473 to 421.479, y: 185.965 to 280.234
# Width: 421, Height: 94.27
banner_svg = make_svg_from_paths(
    white_paths, 
    421, 
    94, 
    "0.473 185.965 421 94.27", 
    bg_rect=(0.473, 185.965, 421, 94.27, "#0076bc")
)
with open('frontend/public/mgt_uzor_banner.svg', 'w', encoding='utf-8') as f:
    f.write(banner_svg)

print("Generated clean SVG files successfully!")
