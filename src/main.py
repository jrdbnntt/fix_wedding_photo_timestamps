import os
import argparse
import re
import time
import shutil
import piexif
import datetime

# Exif Tags: https://www.cipa.jp/std/documents/e/DC-008-2012_E.pdf
TAG_EXIF = "Exif"
TAG_0TH = "0th"
TAG_GPS = "GPS"

DATETIME_TAG_FORMAT = "%Y:%m:%d %H:%M:%S"
TARGET_TIME_ZONE_UTC_OFFSET = -7

# Devices that had their time early by 1 hour
target_devices_off_by_one_hour = [
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
    make = exif_data[TAG_0TH][piexif.ImageIFD.Make].decode(encoding)
    model = exif_data[TAG_0TH][piexif.ImageIFD.Model].decode(encoding)
    img_datetime_original = exif_data[TAG_EXIF][piexif.ExifIFD.DateTimeOriginal].decode(encoding)
    img_datetime_digitized = exif_data[TAG_EXIF][piexif.ExifIFD.DateTimeDigitized].decode(encoding)

    if piexif.GPSIFD.GPSTimeStamp in exif_data[TAG_GPS]:
        gps_timestamp = exif_data[TAG_GPS][piexif.GPSIFD.GPSTimeStamp]
    else:
        gps_timestamp = None
    if piexif.GPSIFD.GPSDateStamp in exif_data[TAG_GPS]:
        gps_datestamp = exif_data[TAG_GPS][piexif.GPSIFD.GPSDateStamp].decode(encoding)
    else:
        gps_datestamp = None

    device = "%s/%s" % (make, model)
    updated = False

    # Correct bad time.
    if device not in target_devices_off_by_one_hour:
        img_datetime_original = increase_image_tag_date_by_one_hour(img_datetime_original)
        img_datetime_digitized = increase_image_tag_date_by_one_hour(img_datetime_digitized)
        exif_data[TAG_EXIF][piexif.ExifIFD.DateTimeOriginal] = img_datetime_original.encode(encoding)
        exif_data[TAG_EXIF][piexif.ExifIFD.DateTimeDigitized] = img_datetime_digitized.encode(encoding)
        updated = True

    # Correct time zone.
    img_datetime_original_dt = datetime.datetime.strptime(img_datetime_original, DATETIME_TAG_FORMAT)
    gps_datetime_expected = img_datetime_original_dt - datetime.timedelta(hours=TARGET_TIME_ZONE_UTC_OFFSET)
    if gps_timestamp is None or gps_datestamp is None:
        invalid_gps_date = True
    else:
        gps_timestamp_actual = datetime.datetime(
            year=gps_datetime_expected.year,
            month=gps_datetime_expected.month,
            day=gps_datetime_expected.day,
            hour=gps_timestamp[0][0],
            minute=gps_timestamp[1][0],
            second=gps_timestamp[2][0],
        )
        gps_datestamp_actual = datetime.datetime.strptime(gps_datestamp, DATETIME_TAG_FORMAT)
        invalid_gps_timestamp = abs((gps_timestamp_actual - gps_datetime_expected)).total_seconds() > 120
        invalid_gps_datestamp = abs((gps_datestamp_actual - gps_datetime_expected)).total_seconds() > 120
        invalid_gps_date = invalid_gps_timestamp or invalid_gps_datestamp
    if invalid_gps_date:
        exif_data[TAG_GPS][piexif.GPSIFD.GPSTimeStamp] = (
            (gps_datetime_expected.hour, 1),
            (gps_datetime_expected.minute, 1),
            (gps_datetime_expected.second, 1)
        )
        exif_data[TAG_GPS][piexif.GPSIFD.GPSDateStamp] = gps_datetime_expected.strftime(DATETIME_TAG_FORMAT) \
            .encode(encoding)
        updated = True

    if not updated:
        return False

    # Move original file to dir.
    path_stored_original = os.path.join(originals_dir, filename)
    path_stored_original = os.path.realpath(path_stored_original)
    os.makedirs(os.path.dirname(path_stored_original), exist_ok=True)
    shutil.move(image_file_path, path_stored_original)

    # Copy original file back to its original location and update it.
    if filename.startswith(copy_prefix):
        copy_prefix = ""
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
