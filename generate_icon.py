import os
from PIL import Image

def generate_high_res_icon(png_path, ico_path):
    try:
        img = Image.open(png_path)
        icon_sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
        img.save(ico_path, format="ICO", sizes=icon_sizes)
        print(f"Successfully generated high-res icon at {ico_path}")
    except Exception as e:
        print(f"Error generating icon: {e}")

if __name__ == "__main__":
    generate_high_res_icon(r"Logo\Archer_Harvest_002.png", r"Logo\icon.ico")
