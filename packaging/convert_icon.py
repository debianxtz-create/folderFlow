from PIL import Image
import os

png_path = "../folderFlow-icon.png"
ico_path = "../folderFlow-icon.ico"

if os.path.exists(png_path):
    img = Image.open(png_path)
    img.save(ico_path, format="ICO", sizes=[(256, 256), (128, 128), (64, 64), (32, 32), (16, 16)])
    print(f"Created {ico_path}")
else:
    print(f"Error: {png_path} not found")
