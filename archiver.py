import argparse
from datetime import datetime
import logging
import logging.handlers
import os
import subprocess
import sys
import tarfile

from common import convert_tgmk, get_filename_range_descriptor, get_smtp_handler, get_temp_file_name, get_size, report


# Specify the slowest expected speed for a du command
DU_MIN_BYTES_PER_SEC = convert_tgmk("500M")

parser = argparse.ArgumentParser(description='Create alphabetical archive volumes of a directory.')
parser.add_argument('source', type=os.path.abspath, help='path to be archived')
parser.add_argument('working_dir', type=os.path.abspath, help='archiver working directory')
parser.add_argument('--destination', default="tar", help='destination folder name')
parser.add_argument('--temp', default="tmp", help='temporary folder name')
parser.add_argument('-m', '--max-size', default='512G', type=convert_tgmk,
                    help='maximum size of an archive file (K, M, G, P supported)')
parser.add_argument('-c', '--checkpoint', type=os.path.abspath, default=None,
                    help='continue an archive process that last archived this path')
parser.add_argument('-s', '--stop', default='100T', type=convert_tgmk,
                    help='maximum size of an destination directory (K, M, G, P supported)')
parser.add_argument('-d', '--debug', action='store_true', help='enable debug logging')

size_cache = {}


def main():

    # Verify and check inputs
    args = parser.parse_args()
    args.destination = str(args.destination)
    args.temp = str(args.temp)

    # Verify and create any directories we might need
    assert os.path.isdir(args.working_dir)
    path = os.path.join(args.working_dir, args.destination)
    if not os.path.exists(path):
        os.makedirs(path)
    path = os.path.join(args.working_dir, args.temp)
    if not os.path.exists(path):
        os.makedirs(path)
    checkpoint_path = os.path.join(args.working_dir, "checkpoint.txt")

    if args.debug:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.getLogger().addHandler(get_smtp_handler())

    # Try to load a checkpoint if one was not specified
    if not args.checkpoint:
        if os.path.exists(checkpoint_path):
            with open(checkpoint_path, 'r') as f:
                args.checkpoint = f.read().rstrip()
            if args.checkpoint == "EOF":
                logging.debug(f"Archiver previously archived all files. Exiting.")
                exit(0)
            logging.debug(f"Archiver found previous checkpoint to be {args.checkpoint}.")

    try:
        logging.debug(f"archiver starting")
        while True:

            # Check if we should continue
            size = get_size(args.working_dir)
            if size > args.stop:
                logging.debug("Archiver terminating as working_dir size limit has been reached.")
                break

            # Create the next archive from the checkpoint
            if not archive_directory(args, args.source):

                # If we get through the entire directory, checkpoint the end offile
                logging.debug("Archiver terminating as it found nothing to backup.")
                with open(checkpoint_path, 'w') as f:
                    f.write(f"EOF\n")
                break

            # Save this spot as a checkpoint
            with open(checkpoint_path, 'w') as f:
                f.write(f"{args.checkpoint}\n")

        logging.debug(f"archiver ending")
    except Exception as e:
        logging.exception('Unhandled Exception', exc_info=e)
        exit(1)


# Function returns True when it has successfully created the next archive file
def archive_directory(args, dir_path):
    logging.debug(f"Starting archive of directory {dir_path}")
    archive = Archive(args.working_dir, dir_path, args.max_size)

    # Get the directory listing in alphabetical order
    directory_list = os.listdir(dir_path)
    directory_list.sort()

    # Run through the contents of this directory
    for listing in directory_list:

        path = os.path.join(dir_path, listing)

        if path == args.working_dir:
            logging.warning(f"Ignoring directory {path} so archiver does not archive itself")
            return False

        # If we have a checkpoint, see if we should skip ahead
        if args.checkpoint:
            # If we have caught up to the last archive, one more skip
            if path == args.checkpoint:
                continue
            # If we are on the path of the checkpoint, go into the next directory
            if path + "/" in args.checkpoint:
                if os.path.isdir(path):
                    if archive_directory(args, path):
                        return True
                continue
            # If we are alphabetically earlier than the checkpint, skip ahead
            if args.checkpoint > path:
                continue

        # This size calculation could be slow, so pass the threshold value
        size = get_size_with_timeout(path, args.max_size - archive.size)
        logging.debug(f"size of {path} is >= {size}")

        # If this item won't fit into the current archive
        if archive.size + size > args.max_size:

            logging.debug(f"{path} is {size} bytes which is too big to fit")
            # If data has been written, break so we close the current archive
            if archive.size > 0:
                break

            # If this is a file, it is bigger than our archive file size
            if os.path.isfile(path):
                logging.error(f"Unable to archive {path} as it is larger ({size}) than "
                              f"the maximum archive size ({args.max_size})")
                exit(1)

            # Try to recursively archive this listing, but continue here on failure
            if archive_directory(args, path):
                return True
            continue

        # Add this listing to our archive
        archive.add(listing, size)

    # A zero size archive means nothing was backed up, so return failure
    if archive.size == 0:
        return False

    # Directory successfully backed up, so close the archive and move forward our restart checkpoint
    archive.rename(directory_list)
    args.checkpoint = os.path.join(dir_path, archive.last_item)
    report(args.working_dir, f"created {archive.name} {archive.size}")
    logging.debug(f"Archiving completed to {args.checkpoint}")
    return True


# Same as get_size but can short-circuit on large directories
def get_size_with_timeout(path, max_size):

    global size_cache
    if path in size_cache:
        logging.debug(f"cache for {path} returning {size_cache[path]}")
        return size_cache[path]

    if os.path.isfile(path) or sys.platform != 'linux':
        return get_size(path)

    # Estimate the maximum number of seconds to wait
    sec = max_size / DU_MIN_BYTES_PER_SEC
    logging.debug(f"calculating the size of {path} with timeout set in {sec} seconds")

    # Try to get the size of path, but only wait as long as an answer is expected to take
    try:
        size = int(subprocess.check_output(['du', '-sb', path], timeout=sec).split()[0])
        size_cache[path] = size
        return size
    except subprocess.TimeoutExpired:
        # Pass through, and we will attempt to get the size in pieces
        logging.debug(f"size calculation timed out. calculating directory size piecemeal.")
        pass

    # Step through each item in the directory
    total_size = 0
    for listing in os.listdir(path):
        subpath = os.path.join(path, listing)
        total_size += get_size_with_timeout(subpath, max_size)

        # Short-circuit this process if we already are beyond the maximum
        if total_size > max_size:
            break
    else:
        logging.debug(f"timeout reached on {path} for {max_size} but size was only {total_size}")

    return total_size


class Archive:

    def __init__(self, dest_dir, source_path, max_size):
        self.dest_dir = dest_dir
        self.source_path = source_path
        self.max_size = max_size

        self.name = f"{get_temp_file_name()}.tar"
        self.path = os.path.join(self.dest_dir, "tmp", self.name)
        self.tmp_flag = True
        self.size = 0
        self.date = None
        self.first_item = None
        self.last_item = None
        assert not os.path.isfile(self.path)
        logging.debug(f"{self}: created for directory {self.source_path}")

    def __del__(self):
        if self.tmp_flag and os.path.isfile(self.path):
            os.remove(self.path)
            logging.debug(f"{self}: deleted")

    def add(self, item, size):
        if self.size + size > self.max_size:
            raise OverflowError

        logging.debug(f"{self}: adding item {item} of size {size}")
        with tarfile.open(self.path, 'a', format=tarfile.GNU_FORMAT) as f:
            try:
                f.add(os.path.join(self.source_path, item))
            # Skip files for which the permission is denied
            except PermissionError:
                logging.error(f"Permission denied attempting to archive item {item} in directory {self.source_path}")
                return

        # For the first item put in, timestamp the archive
        if self.first_item is None:
            self.first_item = item
            self.date = datetime.today().strftime('%Y%m%d')
        self.last_item = item

        # Update our size with the actual value
        self.size = get_size(self.path)

    def rename(self, dir_listing):
        # Don't bother to rename if the archive is empty
        if self.first_item is None:
            return

        # Filename begins with the path with slashes to dots
        name = self.source_path.replace('/', '.').replace('\\', '.')
        while name[0] == ".":
            name = name[1:]

        range_descriptor = get_filename_range_descriptor(self.first_item, self.last_item, dir_listing)
        name = f"{name}.{range_descriptor}.{self.date}.tar"
        archive_path = os.path.join(self.dest_dir, "tar", name)
        assert not os.path.isfile(archive_path)

        os.rename(self.path, archive_path)
        logging.debug(f"{self}: renamed to {name}")
        self.name = name
        self.path = archive_path
        self.tmp_flag = False

    def __str__(self):
        return f"Archive {self.name}"


if __name__ == '__main__':
    main()
