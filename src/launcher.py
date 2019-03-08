#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
import os
import time
import platform
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib, GObject, Gdk
import json
import webbrowser
import traceback
import threading
from src.datalab_api import DataLabAPI


class DataLabLauncher:
    # Class Variables

    glade_file = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "interface.glade")
    )
    local_dockerfile = (
            os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)) + os.sep
    )
    containers_logfile = os.path.abspath(
        os.path.join(os.path.dirname(__file__), os.pardir, "containers.json")
    )
    icon_file = os.path.abspath(
        os.path.join(os.path.dirname(__file__), os.pardir, "assets/logo.svg")
    )

    state_dict = {
        'created': 'Created',
        'running': 'Running...',
        'exited': 'Stopped'
    }

    # Decorator
    def gui_queue(func, *args, **kwargs):
        def inner_func(*args, **kwargs):
            return GObject.idle_add(func, *args, **kwargs)

        return inner_func

    # Input Box Functions

    def get_name_entry(self):
        name_raw = self.name_entry.get_text().replace(" ", "_")
        return name_raw

    def get_project_entry(self):
        return self.proj_entry.get_text()

    def get_machine_box(self):
        index = self.machine_box.get_active()
        return self.machine_list[index][0]

    def get_machine_entry(self):
        return self.machine_entry.get_text()

    @gui_queue
    def set_machine_box(self, machine):
        machine_list_dict = {
            "Local": 0,
            "Cloud": 1
        }
        self.machine_box.set_active(machine_list_dict[machine])

    def set_project_entry(self, string):
        self.project_entry.set_text(string)

    def set_name_entry(self, string):
        self.name_entry.set_text(string)

    def check_entry_match(self):
        name = self.get_name_entry()
        ctrs = self.datalab.get_datalab_ctrs()
        for ctr in ctrs:
            ctr_name = self.datalab.get_ctr_name(ctr)
            if ctr_name == name:
                return ctr
        return False

    @gui_queue
    def check_entries(self):
        # In case previousy disabled:
        self.proj_entry.set_sensitive(True)
        self.machine_entry.set_sensitive(True)
        self.machine_box.set_sensitive(True)
        # Now to make the checks
        name = self.get_name_entry()
        proj = self.get_project_entry()
        ctrs = self.datalab.get_datalab_ctrs()
        deployment = self.get_machine_box()
        gateway = self.get_machine_entry()
        ctr_running = self.datalab.get_running_ctrs()
        ctr_match = self.check_entry_match()
        if ctr_match:
            # is_running = ctr_match in ctr_running
            # TODO: Find out why we can't use ctr_match in
            # ctr_running?
            is_running = self.datalab.get_ctr_name(ctr_match) in [
                self.datalab.get_ctr_name(ctr) for ctr in ctr_running
            ]
            # On Match, we need to overwrite/di Proj ID?
            ctr_proj = self.datalab.get_ctr_project(ctr_match)
            ctr_machine_info = self.datalab.get_ctr_machine_info(ctr_match)
            ctr_deployment = self.datalab.get_ctr_deployment(ctr_match)
            self.proj_entry.set_text(ctr_proj)
            self.proj_entry.set_sensitive(False)
            self.machine_entry.set_text(ctr_machine_info)
            self.machine_entry.set_sensitive(False)
            self.set_machine_box(ctr_deployment)
            self.machine_box.set_sensitive(False)
            if is_running:
                self.update_main_controls(True, "Open", True, "Stop")
            elif ctr_running:
                self.update_main_controls(False, "Start", True, "Remove")
            else:
                self.update_main_controls(True, "Start", True, "Remove")
        else:
            # TODO: Consider Gateway Regex testing here
            if deployment == "Local" and proj == "":
                self.update_main_controls(False, "Create", False, "Remove")
            elif deployment == "Cloud" and (proj == "" or gateway == ""):
                self.update_main_controls(False, "Create", False, "Remove")
            else:
                self.update_main_controls(True, "Create", False, "Remove")

    # Container Functions

    def start_ctr(self, ctr):
        self.switch_spinner(True)
        self.switch_main_controls(False)
        logging.info("Starting Container: " + self.datalab.get_ctr_name(ctr))
        self.write_to_statusbar("Starting Container: " + self.datalab.get_ctr_name(ctr))
        try:
            self.datalab.start_container(ctr)
            logging.info("Container started")
            self.write_to_statusbar("Container started")
        except Exception as e:
            logging.info("Failed to start container")
            self.write_error_to_statusbar("Failed to start container")
        self.update_ctr_list()
        self.switch_spinner(False)
        self.switch_main_controls(True)

    def stop_ctr(self, ctr):
        self.switch_spinner(True)
        self.switch_main_controls(False)
        logging.info("Stopping Container: " + self.datalab.get_ctr_name(ctr))
        self.write_to_statusbar("Stopping Container: " + self.datalab.get_ctr_name(ctr))
        try:
            self.datalab.stop_container(ctr)
            logging.info("Container stopped")
            self.write_to_statusbar("Container stopped")
        except Exception as e:
            logging.info("Failed to stop container")
            self.write_error_to_statusbar("Failed to stop container")
        self.update_ctr_list()
        self.switch_spinner(False)
        self.switch_main_controls(True)

    def remove_ctr(self, ctr):
        self.switch_spinner(True)
        self.switch_main_controls(False)
        logging.info("Removing Container: " + self.datalab.get_ctr_name(ctr))
        self.write_to_statusbar("Removing Container: " + self.datalab.get_ctr_name(ctr))
        try:
            self.datalab.remove_container(ctr)
            logging.info("Container removed")
            self.write_to_statusbar("Container removed")
        except Exception as e:
            logging.info("Failed to remove container")
            self.write_error_to_statusbar("Failed to remove container")
        self.update_ctr_list()
        self.switch_spinner(False)
        self.switch_main_controls(True)

    def create_ctr(self, name, project_id, deployment, gateway):
        self.switch_spinner(True)
        self.switch_main_controls(False)
        if deployment == "Local":
            gateway = None
        logging.info(
            "Creating Container: Deployment = %s, Project ID = %s, Name = %s"
            % (deployment, project_id, (name or "<Auto-Generated>"))
        )
        self.write_to_statusbar(
            "Creating Container: Deployment = %s, Project ID = %s, Name = %s"
            % (deployment, project_id, (name or "<Auto-Generated>"),)
        )
        try:
            ctr = self.datalab.create_container(
                name, project_id, deployment, gateway,
                self.settings["local_drive"], self.settings["drives"]
            )
            logging.info("Container created")
            self.write_to_statusbar("Container created")
            ctr_name = self.datalab.get_ctr_name(ctr)
            self.set_name_entry(ctr_name)
        except Exception as e:
            logging.info("Failed to create container")
            traceback.print_exc()
            self.write_error_to_statusbar(
                "Failed to create container: %s" % e.message
            )
        self.update_ctr_list()
        self.switch_spinner(False)
        self.switch_main_controls(True)

    def open_ctr(self, ctr):
        self.switch_spinner(True)
        self.switch_main_controls(False)
        ctr_address = self.datalab.get_ctr_address(ctr)
        ctr_name = self.datalab.get_ctr_name(ctr)
        countdown = self.settings["opening_countdown"]
        logging.info(
            "Opening %s at %s in %s seconds" % (ctr_name, ctr_address, countdown)
        )
        while countdown > 0:
            self.write_to_statusbar(
                "Opening %s at %s in %s..." % (ctr_name, ctr_address, countdown)
            )
            time.sleep(1)
            countdown = countdown - 1
        try:
            webbrowser.open(ctr_address, new=True)
            self.write_to_statusbar("DataLab opened at %s" % ctr_address)
            logging.info("DataLab opened at %s" % ctr_address)
        except Exception as e:
            logging.error("Failed to open DataLab in browser")
            self.write_error_to_statusbar("Failed to open DataLab in browser")
        self.update_ctr_list()
        self.switch_spinner(False)
        self.switch_main_controls(True)

    # Image Functions

    def run_update(self):
        self.switch_spinner(True)
        self.switch_main_controls(False)
        logging.info("Updating Image")
        self.write_to_statusbar("Updating DataLab Image...")
        try:
            self.change_check_label("Image", "Updating...", colour="#FF9900")
            self.datalab.update_image(self.settings["latest_dockerfile"])
            with open(self.settings["latest_dockerfile"] + "Dockerfile",
                      'r') as latest_file:
                latest_content = latest_file.read()
                self.datalab.update_local_dockerfile(
                    self.local_dockerfile, latest_content
                )
            self.write_to_statusbar("DataLab Image successfully updated")
            logging.info("Image updated")
            self.change_check_label("Image", "Update Successful", colour="green")
        except Exception as e:
            logging.error("Failed to update Image")
            self.write_error_to_statusbar("Failed to update Image: %s" % e.message)
            self.change_check_label("Image", "Update Failed", colour="red")
        self.update_ctr_list()
        self.switch_spinner(False)
        self.switch_main_controls(True)

    # UI Function Calls

    def on_main_negative_clicked(self, widget):
        if widget.get_label() == "Stop":
            threading.Thread(
                target=self.stop_ctr,
                args=(self.check_entry_match(),)
            ).start()
        elif widget.get_label() == "Remove":
            threading.Thread(
                target=self.remove_ctr,
                args=(self.check_entry_match(),)
            ).start()

    def on_main_positive_clicked(self, widget):
        if widget.get_label() == "Start":
            threading.Thread(
                target=self.start_ctr,
                args=(self.check_entry_match(),)
            ).start()
        elif widget.get_label() == "Create":
            threading.Thread(
                target=self.create_ctr,
                args=(
                    self.get_name_entry(),
                    self.get_project_entry(),
                    self.get_machine_box(),
                    self.get_machine_entry()
                )
            ).start()
        elif widget.get_label() == "Open":
            threading.Thread(
                target=self.open_ctr,
                args=(self.check_entry_match(),)
            ).start()

    @gui_queue
    def on_select_container(self, container_view, row, column):
        model, path_list = container_view.get_selection().get_selected_rows()
        tree_iter = model.get_iter(path_list[0])
        values = []
        for col in range(model.get_n_columns()):
            values.append(model.get_value(tree_iter, col))
        model_col_dict = {
            "Name": 1,
            "Project ID": 2,
            "Deployment": 5,
            "Machine Info": 6
        }
        ctr_name = values[model_col_dict["Name"]]
        ctr_proj = values[model_col_dict["Project ID"]]
        ctr_deployment = values[model_col_dict["Deployment"]]
        ctr_machine_info = values[model_col_dict["Machine Info"]]
        self.name_entry.set_text(ctr_name)
        self.proj_entry.set_text(ctr_proj)
        self.set_machine_box(ctr_deployment)
        self.auto_hide_machine_entry()
        self.machine_entry.set_text(ctr_machine_info)
        self.switch_main_controls(True)

    def on_update_link_clicked(self, arg1, arg2):
        threading.Thread(target=self.run_update).start()

    def on_project_entry_changed(self, widget):
        self.check_entries()

    def on_name_entry_changed(self, widget):
        self.check_entries()

    def on_machine_box_changed(self, widget):
        self.auto_hide_machine_entry()
        self.check_entries()

    def on_machine_entry_changed(self, widget):
        self.check_entries()

    def on_toggle_option(self):
        return 0

    def on_status_positive_clicked(self, widget):
        if widget.get_label() == "Restart":
            logging.info("Restarting Start Up Checks")
            threading.Thread(target=self.run_startup_checks).start()

    @staticmethod
    def on_status_negative_clicked(widget):
        if widget.get_label() == "Close":
            logging.info("Close button pressed")
            Gtk.mainquit()
            logging.info("DataLab Launcher Closed")

    # UI Management Functions

    def null_callback(self):
        return 0

    @gui_queue
    def update_main_controls(self, pos_state, pos_label, neg_state, neg_label):
        self.main_positive.set_sensitive(pos_state)
        self.main_negative.set_sensitive(neg_state)
        self.main_positive.set_label(pos_label)
        self.main_negative.set_label(neg_label)

    @gui_queue
    def auto_hide_machine_entry(self):
        machine = self.get_machine_box()
        if machine == "Local":
            self.machine_entry.hide()
        elif machine == "Cloud":
            self.machine_entry.show()

    @gui_queue
    def switch_spinner(self, state):
        if state is False:
            self.status_spinner.stop()
        elif state is True:
            self.status_spinner.start()

    # @gui_queue
    def change_check_label(self, label, string, colour="black"):
        def run_function():
            label_dict = {
                "API": self.api_label,
                "Drive": self.drive_label,
                "Image": self.image_label,
            }
            label_dict[label].set_markup(
                "<span color=\"" + colour + "\">" + string + "</span>"
            )

        return run_function()

    @gui_queue
    def update_ctr_list(self):
        logging.debug("Updating Container List")
        ctrs_info = self.datalab.get_ctrs_info()
        self.ctr_list.clear()
        for ctr_info in ctrs_info:
            row = [
                ctr_info["Status"],
                ctr_info["Name"],
                ctr_info["Project ID"],
                ctr_info["Version"],
                ctr_info["User"],
                ctr_info["Deployment"],
                ctr_info["Machine Info"]
            ]
            self.ctr_list.append(row=row)
        logging.debug("Container List Updated")

    @gui_queue
    def switch_main_controls(self, state):
        logging.debug("Switching main controls: state = " + str(state))
        if state is True or state == False:
            self.main_positive.set_sensitive(state)
            self.main_negative.set_sensitive(state)
            self.proj_entry.set_sensitive(state)
            self.name_entry.set_sensitive(state)
            self.ctr_view.set_sensitive(state)
            self.machine_box.set_sensitive(state)
            self.machine_entry.set_sensitive(state)
            if state is True:
                self.check_entries()
            logging.debug("Main controls switched")
        else:
            logging.error("Unable to switch main controls state")
            raise ValueError("Switch state invalid. state = " + str(state))

    @gui_queue
    def switch_status_controls(self, state, pos_label=None, neg_label=None):
        logging.debug("Switching status controls: state = " + str(state))
        if state is True:
            if pos_label is not None and neg_label is not None:
                self.status_positive.set_label(pos_label)
                self.status_negative.set_label(neg_label)
                logging.debug("Status controls labels changed")
            self.status_positive.show()
            self.status_negative.show()
            self.status_positive.set_sensitive(True)
            self.status_negative.set_sensitive(True)
            logging.debug("Status controls switched")
        elif state is False:
            self.status_positive.set_sensitive(False)
            self.status_negative.set_sensitive(False)
            self.status_positive.hide()
            self.status_negative.hide()
            logging.debug("Status controls switched")
        else:
            logging.error("Unable to switch status controls state")
            raise ValueError("Switch state invalid. state = " + str(state))

    @gui_queue
    def write_to_statusbar(self, string):
        self.status_label.set_text(string)

    @gui_queue
    def write_error_to_statusbar(self, string):
        self.status_label.set_markup(
            "<span color=\"red\">Error: " + str(string) + "</span>"
        )

    def update_check_label(self, check, string, color):
        return 0

    # Startup Functions

    def load_settings(self):
        return 0

    def check_shared_drives(self):
        shared_dockerfile = self.settings["latest_dockerfile"]
        if os.access(os.path.expanduser(shared_dockerfile) + "Dockerfile",
                     os.R_OK) is False:
            logging.error("Failed")
            return False
        drives = self.settings["drives"]
        accessible_drives = []
        test_conditions = {
            "ro": os.R_OK,
            "rw": os.F_OK
        }
        for drive in drives:
            access = drive["Access"]
            path = drive["Path"]
            if os.access(os.path.expanduser(path), test_conditions[access]):
                accessible_drives.append(drive)
        if len(accessible_drives) == len(drives):
            return "All"
        elif len(accessible_drives) > 0:
            # return "Some"
            # Disabled until Shared Drives managed better
            return False
        else:
            return False

    def run_startup_checks(self):
        logging.debug("Detached Startup Checks Thread")
        check_step = "UI Prep"
        try:
            # Ensure all controls are disabled prior to checks
            self.switch_main_controls(False)
            self.switch_status_controls(False)
            # Ensure all labels set to neutral
            self.change_check_label("API", "Unchecked")
            self.change_check_label("Drive", "Unchecked")
            self.change_check_label("Image", "Unchecked")
            # Start the spinner
            self.status_spinner.show()
            self.switch_spinner(True)
            # Annoyingly, we need to hide machine_entry in python
            self.machine_entry.hide()
            # Attempt to perform and resolve all checks
            # First: Check/Instantiate Docker API Connection
            check_step = "API"
            logging.info("Checking DataLab - Docker API Connection...")
            self.datalab = DataLabAPI(
                self.os_type, self.settings['docker_client_timeout'],
                self.containers_logfile, self.settings['local_drive']
            )
            self.change_check_label("API", "Connected", "green")
            logging.info("DataLab API Check Successful")
            # Second: Check Drives are present
            check_step = "Drive"
            logging.info("Checking Shared Drive availability")
            self.drives_present = self.check_shared_drives()
            if self.drives_present is False:
                logging.info("Shared Drives not accessible")
                self.change_check_label("Drive", "Not Available", "red")
                raise Exception("Cannot access Shared Drives")
            elif self.drives_present == "All":
                self.change_check_label("Drive", "Available", "green")
                logging.info("Shared Drives partially accessible")
            elif self.drives_present == "Some":
                self.change_check_label("Drive", "Some Available", "#FF9900")
                logging.info("Shared Drives partially accessible")

            # Third: DataLab Image Checks
            check_step = "Image"
            logging.info("Checking DataLab Image")
            self.image_loaded = self.datalab.check_image_loaded()
            if self.image_loaded is False:
                self.change_check_label("Image", "Loading...", "#FF9900")
                logging.info("No DataLab Image loaded")
                self.write_to_statusbar("Pulling DataLab Image...")
                #  - If not: Can we access the shared Dockerfile?
                pull_outcome = None
                if self.drives_present in ["All", "Some"]:
                    #  - If so, pull Dockerfile
                    pull_outcome = self.datalab.pull_image(
                        "Latest", self.settings['latest_dockerfile']
                    )
                    if pull_outcome is False:
                        pull_outcome = self.datalab.pull_image(
                            "Local", self.local_dockerfile
                        )
                        if pull_outcome is False:
                            pull_outcome = self.datalab.pull_image("Base")
                            if pull_outcome is False:
                                raise Exception("Unable to pull any Dockerfile")
                elif self.drives_present is False:
                    #  - Otherwise; pull from existing/base file
                    pull_outcome = self.datalab.pull_image("Local",
                                                           self.local_dockerfile)
                    if pull_outcome is False:
                        pull_outcome = self.datalab.pull_image("Base")
                        if pull_outcome is False:
                            raise Exception("Failed to pull DataLab Image")
                # After pulling an image, we update our local dockerfile to
                # match Image pulled
                logging.debug("Updating Local Dockerfile to match Image")
                self.datalab.update_local_dockerfile(self.local_dockerfile,
                                                     pull_outcome)
                self.change_check_label("Image", "Ready", "green")
                logging.debug("Local Dockerfile Updated")
            elif self.image_loaded is True:
                self.change_check_label("Image", "Ready", "green")
                logging.info("DataLab Image already loaded")
            # Finally: Check for updates
            check_step = "Update"
            logging.info("Checking for updates")
            self.update_available = self.datalab.compare_dockerfiles(
                self.local_dockerfile, self.settings['latest_dockerfile']
            )
            if self.update_available is False:
                logging.info("Update Available")
                self.change_check_label(
                    "Image", "<a href='#'>Update Available</a>", "blue"
                )
            else:
                logging.info("No Update Available")
            check_step = "Cleanup"
            self.switch_main_controls(True)
            self.write_to_statusbar("Startup Checks Complete. Launcher Ready.")
            logging.info("All Startup Checks complete")
            logging.info("Updating Container List post-checks")
            self.update_ctr_list()
            # Stop the spinner
            self.switch_spinner(False)
        except Exception as e:
            self.switch_spinner(False)
            logging.error("Startup Checks stopped unexpectedly")
            logging.error("Failed at check step : " + check_step)
            self.write_error_to_statusbar(e.message)
            logging.error(traceback.print_exc())
            self.switch_status_controls(True, "Restart", "Close")
            if check_step == "API":
                self.change_check_label("API", "Failed", "red")
            elif check_step == "Drive":
                self.change_check_label("Drive", "Failed", "red")
            elif check_step == "Image":
                self.change_check_label("Image", "Failed", "red")

    def __init__(self, settings_file):
        # We've started the program. Log it
        logging.info("DataLab Launcher Loading...")
        # Now, let's determine the Operating System
        self.os_type = platform.system()
        logging.debug("Detected Operating System: " + self.os_type)
        # Now let's pull our settings
        logging.debug("Pulling settings from " + settings_file)
        with open(settings_file) as data:
            self.settings = json.load(data)
        logging.debug("Settings pulled")
        # Instantiate GUI via Glade
        logging.debug("Binding UI Components from Glade File...")
        self.glade = Gtk.Builder()
        self.glade.add_from_file(self.glade_file)
        self.glade.connect_signals(self)
        self.glade.get_object("main_window").show_all()
        self.glade.get_object("main_window").set_icon_from_file(self.icon_file)
        # Status Check Labels
        self.api_label = self.glade.get_object("api_label")
        self.image_label = self.glade.get_object("image_label")
        self.drive_label = self.glade.get_object("drive_label")
        # Hook Models and Views
        self.ctr_view = self.glade.get_object("container_view")
        self.ctr_list = self.ctr_view.get_model()
        self.proj_entry = self.glade.get_object("project_entry")
        self.name_entry = self.glade.get_object("name_entry")
        self.machine_box = self.glade.get_object("machine_box")
        self.machine_list = self.machine_box.get_model()
        self.machine_entry = self.glade.get_object("machine_entry")
        # Hook Controls
        self.main_negative = self.glade.get_object("main_positive")
        self.main_positive = self.glade.get_object("main_negative")
        self.update_button = self.glade.get_object("update_button")
        # Hook Status Bar Objects
        self.status_label = self.glade.get_object("status_label")
        self.status_spinner = self.glade.get_object("status_spinner")
        self.status_buttons = self.glade.get_object("status_buttons")
        self.status_positive = self.glade.get_object("status_positive")
        self.status_negative = self.glade.get_object("status_negative")
        # Hook Menu Items
        self.open_on_start = self.glade.get_object("open_on_start")
        logging.debug("UI Components bound")
        # Run Start Up Checks
        # - Separate thread to allow for user input
        self.write_to_statusbar("Running Start Up Checks...")
        logging.info("Running Start Up Checks...")
        threading.Thread(target=self.run_startup_checks).start()
