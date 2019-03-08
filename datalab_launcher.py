from src import launcher
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk
import sys
Gdk.threads_init()
import argparse
import logging
import os

# TODO: Implement Regex check/replace on ctr names (i.e. whitespace; single character)
# TODO: Test Cloud Project
# TODO: Sanitize Error Messages
# TODO: Properly handle old images
# TODO: Fix Pulling User and Project Info
# TODO: Fix Menubar and Options
# TODO: Tooltip for Missing Shared Drives
# TODO: Enter button on positive
# TODO: Try to allow DataLab to work without Shared Drives
# TODO: Incorporate more Shared Drive Checks
# TODO: Add Restart/Close buttons to failed DataLab Update
# TODO: Allow access to container by SSH?

if __name__ == "__main__":

	try:
		# Set Global Variables
		log_file = "launcher.log"
		# Pull Command-Line Arguments
		parser = argparse.ArgumentParser()
		parser.add_argument(
				'-d', '--debug',
				help="Print lots of debugging statements",
				action="store_const", dest="loglevel", const=logging.DEBUG,
				default=logging.WARNING,
		)
		parser.add_argument(
				'-v', '--verbose',
				help="Be verbose",
				action="store_const", dest="loglevel", const=logging.INFO,
		)
		# FOR DEBUGGING
		loglevel = logging.DEBUG
		args = parser.parse_args()
		# Start Root Logger
		root_logger = logging.getLogger()
		root_logger.setLevel(logging.DEBUG)
		# Configure Console Logging
		stdout_handler = logging.StreamHandler(sys.stdout)
		stdout_handler.setLevel(args.loglevel)
		stdout_formatter = logging.Formatter(
			'%(asctime)s - %(name)s - %(levelname)s - %(message)s'
		)
		stdout_handler.setFormatter(stdout_formatter)
		root_logger.addHandler(stdout_handler)
		# Configure LogFile Logging
		file_handler = logging.FileHandler(log_file, "w", encoding=None, delay="true")
		file_handler.setLevel(logging.DEBUG)
		file_formatter = logging.Formatter(
			'%(asctime)s - %(name)s - %(levelname)s - %(message)s'
		)
		file_handler.setFormatter(file_formatter)
		root_logger.addHandler(file_handler)
		# Start the UI
		settings_file = os.path.join(os.path.dirname(__file__), 'settings.json')
		instance = launcher.DataLabLauncher(settings_file=settings_file)
		Gdk.threads_init()
		Gtk.main()
	except KeyboardInterrupt:
		pass

