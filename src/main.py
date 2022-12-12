import os
import argparse
import re
import time
import shutil
import piexif
import datetime

# Exif Tags: https://www.cipa.jp/std/documents/e/DC-008-2012_E.pdf
TAG_EXIF = "Exif"
TAG_EXIF_DATE_TIME_ORIGINAL = 36867
TAG_EXIF_DATE_TIME_DIGITIZED = 36868
TAG_0TH = "0th"
TAG_0TH_MAKE = 271
TAG_0TH_MODEL = 272

DATETIME_TAG_FORMAT = "%Y:%m:%d %H:%M:%S"

# Devices that had their time early by 1 hour
target_devices = [
    "SONY/ILCE-7M3"
]


def main():
    args = parse_args()
    originals_dir = os.path.join(args.src_dir, args.originals_dir, str(int(time.time())))
    image_file_paths = collect_file_paths(args.src_dir, ["jpeg", "jpg"])
    image_file_paths.sort(key=parse_int_from_filename)
    print("Found %d photos in '%s'" % (len(image_file_paths), args.src_dir))
    updates = 0
    for path in image_file_paths:
        if process_image_file(
                image_file_path=path,
                originals_dir=originals_dir,
                copy_prefix=args.copy_prefix
        ):
            print("Updated %s" % os.path.basename(path))
            updates += 1
    print("Updated %d of %d photos" % (updates, len(image_file_paths)))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("-d", "--src_dir", dest="src_dir",
                        help="Directory containing image files to fix",
                        default="../test_photos")
    parser.add_argument("-p", "--prefix", dest="copy_prefix",
                        help="Prefix to add to updated/copied files",
                        default="metafix_")
    parser.add_argument("-o", "--originals_dir", dest="originals_dir",
                        help="Directory to move originals that are to be replaced to, relative to src_dir",
                        default="originals")
    return parser.parse_args()


def collect_file_paths(src_dir: str, extensions: list[str]) -> list[str]:
    filenames = []
    for filename in os.listdir(src_dir):
        ext = filename.split(".")[-1]
        if ext in extensions:
            filenames.append(os.path.abspath(os.path.join(src_dir, filename)))
    return filenames


def parse_int_from_filename(path: str) -> int:
    filename = os.path.basename(path)
    return int(re.search(r'\d+', filename).group())


def process_image_file(image_file_path: str, originals_dir: str, copy_prefix: str) -> bool:
    image_file_path = os.path.realpath(image_file_path)
    filename = os.path.basename(image_file_path)

    encoding = "UTF-8"
    exif_data = piexif.load(image_file_path)
    make = exif_data[TAG_0TH][TAG_0TH_MAKE].decode(encoding)
    model = exif_data[TAG_0TH][TAG_0TH_MODEL].decode(encoding)
    device = "%s/%s" % (make, model)

    if device not in target_devices:
        return False

    # Update timestamps
    img_datetime_original = exif_data[TAG_EXIF][TAG_EXIF_DATE_TIME_ORIGINAL].decode(encoding)
    img_datetime_digitized = exif_data[TAG_EXIF][TAG_EXIF_DATE_TIME_DIGITIZED].decode(encoding)
    img_datetime_original = increase_image_tag_date_by_one_hour(img_datetime_original)
    img_datetime_digitized = increase_image_tag_date_by_one_hour(img_datetime_digitized)
    exif_data[TAG_EXIF][TAG_EXIF_DATE_TIME_ORIGINAL] = img_datetime_original.encode(encoding)
    exif_data[TAG_EXIF][TAG_EXIF_DATE_TIME_DIGITIZED] = img_datetime_digitized.encode(encoding)

    # Move original file to dir.
    path_stored_original = os.path.join(originals_dir, filename)
    path_stored_original = os.path.realpath(path_stored_original)
    os.makedirs(os.path.dirname(path_stored_original), exist_ok=True)
    shutil.move(image_file_path, path_stored_original)

    # Copy original file back to its original location and update it.
    image_file_path = os.path.join(os.path.dirname(image_file_path), copy_prefix + filename)
    shutil.copyfile(path_stored_original, image_file_path)
    piexif.insert(piexif.dump(exif_data), image_file_path)

    return True


def increase_image_tag_date_by_one_hour(tag_datetime: str) -> str:
    dt = datetime.datetime.strptime(tag_datetime, DATETIME_TAG_FORMAT)
    dt += datetime.timedelta(hours=1)
    return dt.strftime(DATETIME_TAG_FORMAT)


if __name__ == "__main__":
    main()
