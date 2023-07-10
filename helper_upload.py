"""

Helper function to upload an png image given its bytestream

modal deploy helper_upload.py
"""

import os
import sys
from io import StringIO

from modal import Image, Stub



image = (
    Image.debian_slim()
    .pip_install_from_requirements("requirements_upload.txt")
    .env(
        {
            "CLOUDINARY_CLOUD_NAME": os.environ["CLOUDINARY_CLOUD_NAME"],
            "CLOUDINARY_API_KEY": os.environ["CLOUDINARY_API_KEY"],
            "CLOUDINARY_API_SECRET": os.environ["CLOUDINARY_API_SECRET"],
        }
    )
)

stub = Stub("image-upload-shared")


@stub.function(image=image, timeout=30)
def upload_image(image_data):
    import cloudinary.uploader

    with open("image.png", "wb") as f:
        f.write(image_data)

    cloudinary.config(
        cloud_name=os.environ["CLOUDINARY_CLOUD_NAME"],
        api_key=os.environ["CLOUDINARY_API_KEY"],
        api_secret=os.environ["CLOUDINARY_API_SECRET"],
    )

    # reject if file size is too big
    reply = cloudinary.uploader.upload("image.png")
    image_url = reply["secure_url"]
    print("image_url")
    print(image_url)
    return image_url
