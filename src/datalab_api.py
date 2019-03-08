import logging
from io import BytesIO
import re
import json
import os
from haikunator import Haikunator


class DataLabAPI:

	# Global Variables
	docker = None
	cli = None
	cli_timeout = None
	os_type = None
	ctrs = None
	ctrs_log = None

	# Container Status Dict
	ctr_status_dict = {
		u"running": "Running...",
		u"paused": "Paused",
		u"exited": "Stopped",
		u"created": "Created",
		u"restarting": "Restarting..."
	}

	# Container Log Function

	def load_containers_log(self):
		with open(self.ctrs_logfile, 'r') as logfile:
			ctrs_log = json.load(logfile)
			self.ctrs_log = ctrs_log

	def save_containers_log(self):
		with open(self.ctrs_logfile, 'w') as logfile:
			json.dump(self.ctrs_log, logfile)

	# Drive Functions
	
	def dockerfy_path(self, path):
		if self.os_type == "Linux":
			return os.path.abspath(path)
		elif self.os_type == "Windows":
			path = os.path.abspath(path)
			return re.sub(r"^([A-Z])\:","/\\1", os.path.abspath(path))
		else:
			return path

	# Dockerfile Functions

	@staticmethod
	def update_local_dockerfile(local, new_contents):
		with open(local + "Dockerfile", 'w') as local_file:
			local_file.write(new_contents)

	@staticmethod
	def compare_dockerfiles(local, latest):
		local = os.path.join(os.getcwd(), local, "Dockerfile")
		latest = os.path.join(latest, "Dockerfile")
		with open(local, 'r') as local_file:
			local_content = local_file.readlines()
		with open(latest, 'r') as latest_file:
			latest_content = latest_file.readlines()	
		for i, val in enumerate(local_content):
			if local_content[i] != latest_content[i]:
				return False
		return True

	# Container Functions
	
	def gen_ctr_name(self):
		return Haikunator().haikunate(delimiter="_",token_length=0)

	def get_datalab_ctrs(self):
		ctrs = self.cli.containers.list(all=True)
		return [
			ctr for ctr in ctrs
			if (u"dll_image" in ctr.attrs[u"Config"][u"Labels"]
				and self.get_ctr_image(ctr) == u"datalab")
		]

	def get_running_ctrs(self):
		datalab_ctrs = self.get_datalab_ctrs()
		return [
			ctr for ctr in datalab_ctrs
			if (self.get_ctr_state(ctr) == u"running")
		]

	def is_ctr_running(self, ctr):
		return self.get_ctr_state(ctr) == u"running"

	@staticmethod
	def start_container(ctr):
		ctr.start()

	@staticmethod
	def stop_container(ctr):
		ctr.stop()

	def remove_container(self, ctr):
		ctr_name = self.get_ctr_name(ctr)
		ctr.remove()
		self.ctrs_log.pop(ctr_name, None)
		self.save_containers_log()

	def create_container(
			self, name, project_id, deployment, gateway, local_drive, drives,
			local_port=8081
	):
		binds = {}
		if name == "":
			name = self.gen_ctr_name()
		container_drive = os.path.join(os.path.abspath(local_drive), "containers", name)
		notebooks_drive = os.path.join(os.path.abspath(local_drive), "my_notebooks")
		# Create if they don't exist
		if not os.path.exists(container_drive):
			logging.info("CTR DRIVE NOT EXISTS %s:", container_drive)
			os.makedirs(container_drive)
		if not os.path.exists(notebooks_drive):
			os.makedirs(notebooks_drive)
		binds[self.dockerfy_path(container_drive)] = {
			'bind': '/content/datalab/',
			"mode": 'rw'
		}
		binds[self.dockerfy_path(notebooks_drive)] = {
			'bind': '/content/datalab/workspace/my_notebooks',
			"mode": 'rw'
		}
		for drive in drives:
			binds[self.dockerfy_path(drive['Path'])] = {
				'bind' : drive["Mountpoint"],
				"mode" : drive['Access']
			}
		kwargs = {
			"environment" : {
				"PROJECT_ID": project_id,
				# TODO: Check this doesn't need to be GCE when using cloud
				"DATALAB_ENV": "local",
			},
			"labels": {
				"dll_address": "http://localhost:%s/" % (local_port,),
				"dll_deployment": deployment,
				"dll_machine_info": (gateway or "-")
			},
			"volumes": binds,
			"ports": {'8080': ("127.0.0.1", local_port)},
			"stdin_open": True,
			"tty": True,
			"name": name,
			"image": "dll_datalab:latest",
			"entrypoint": ["/datalab/run.sh"]
		}
		if name:
			kwargs["name"] = name
		if gateway:
			kwargs["environment"]["GATEWAY_VM"] = gateway
		ctr = self.cli.containers.create(**kwargs)
		# Alter startup path
		datalab_settings = os.path.join(container_drive, ".config","settings.json")
		if not os.path.exists(os.path.dirname(datalab_settings)):
			os.makedirs(os.path.dirname(datalab_settings))
		with open(datalab_settings, 'w') as f:
			f.write('{"startuppath":"/tree/datalab/workspace"}')
		self.ctrs_log[name] = {
			"PROJECT_ID": project_id,
			"USER": "-"
		}
		self.save_containers_log()
		return ctr

	def get_ctr_project(self, ctr):
		if self.is_ctr_running(ctr):
			try:
				# TODO: Look for a way of updating project if it changes?
				# Raising here to break previous method
				env = ctr.exec_run("bash -c printenv", tty=True)
				project_raw = re.search(r"^PROJECT_ID=(.*)$", env, re.MULTILINE)
				project_clean = (
					project_raw
					.groups()[0]
					.replace('\r', '')
					.replace('\n', '')
				)
				self.ctrs_log[self.get_ctr_name(ctr)]["PROJECT_ID"] = project_clean
				self.save_containers_log()
				return project_clean
			except Exception as e:
				logging.info("Failed to extract Project ID")
		try:
			last_project = self.ctrs_log[self.get_ctr_name(ctr)]["PROJECT_ID"]
			if last_project is None:
				pass
				# raise
			return last_project
		except Exception as e:
			logging.error("Failed to load previous Project ID")
			return "-"

	def get_ctr_user(self, ctr):
		credentials_file = os.path.join(
			os.path.abspath(self.local_drive),
			"containers",
			self.get_ctr_name(ctr),
			".config",
			"credentials"
		)
		if os.path.exists(credentials_file):
			try:
				ctr_user = None
				with open(credentials_file, 'r') as file:
					creds = json.load(file)
					try:
						ctr_user = creds['data'][0]['key']['account']
					except Exception as e:
						logging.debug("Cannot pull user from credentials file")
				if ctr_user is None:
					logging.error("Cannot pull ctr_user from credentials file")
					self.ctrs_log[self.get_ctr_name(ctr)]["USER"] = "-"
					self.save_containers_log()
					return "-"
				self.ctrs_log[self.get_ctr_name(ctr)]["USER"] = ctr_user
				self.save_containers_log()
				return ctr_user
			except Exception as e:
				logging.error("Failed to extract User Account")
		try:
			return self.ctrs_log[self.get_ctr_name(ctr)]["USER"]
		except Exception as e:
			logging.error("Failed to load previous User Account")
			return "-"

	@staticmethod
	def get_ctr_name(ctr):
		return ctr.name

	@staticmethod
	def get_ctr_image(ctr):
		return ctr.attrs[u"Config"][u"Labels"][u"dll_image"]

	@staticmethod
	def get_ctr_version(ctr):
		return ctr.attrs[u"Config"][u"Labels"][u"dll_version"]

	@staticmethod
	def get_ctr_deployment(ctr):
		return ctr.attrs[u"Config"][u"Labels"][u"dll_deployment"]

	@staticmethod
	def get_ctr_address(ctr):
		return ctr.attrs[u"Config"][u"Labels"][u"dll_address"]

	@staticmethod
	def get_ctr_machine_info(ctr):
		return ctr.attrs[u"Config"][u"Labels"][u"dll_machine_info"]

	@staticmethod
	def get_ctr_state(ctr):
		return ctr.attrs[u"State"][u"Status"]

	def get_ctrs_info(self):
		datalab_ctrs = self.get_datalab_ctrs()
		ctrs_info = []
		for ctr in datalab_ctrs:
			ctr_info = {}
			ctr_state = self.get_ctr_state(ctr)
			ctr_info["Status"] = self.ctr_status_dict[ctr_state]
			ctr_info["Name"] = self.get_ctr_name(ctr)
			ctr_info["Project ID"] = self.get_ctr_project(ctr)
			ctr_info["User"] = self.get_ctr_user(ctr)
			ctr_info["Version"] = self.get_ctr_version(ctr)
			ctr_info["Deployment"] = self.get_ctr_deployment(ctr)
			ctr_info["Address"] = self.get_ctr_address(ctr)
			ctr_info["Machine Info"] = self.get_ctr_machine_info(ctr)
			ctrs_info.append(ctr_info)
		return ctrs_info

	# Image Functions

	def check_image_loaded(self):
		imgs = self.cli.images.list(all=True)
		datalab_images = [img for img in imgs if u"dll_datalab:latest" in img.tags]
		return True if len(datalab_images) > 0 else False

	def update_image(self, dockerfile):
		logging.debug("Dockerfile used: " + dockerfile)
		logging.debug("Building image as dll_datalab:latest")
		self.cli.images.build(
			path=dockerfile,
			rm=True,
			pull=True,
			tag="dll_datalab:latest"
		)
		logging.debug("Image successfully updated")

	def pull_image(self, image_type, dockerfile=None):
		try:
			logging.debug("Building Image of type: " + image_type)
			if image_type is "Base":
				dockerfile_str = (
					"# Base Image\nFROM gcr.io/cloud-datalab/datalab:local"
					"\nLABEL \"dll_image\"=\"datalab\""
					"\nLABEL\"LABEL\"dll_version\"=\"base\""
				)
				dockerfile = BytesIO(dockerfile_str)
				logging.debug("Building image as dll_datalab:latest")
				self.cli.images.build(
					path=dockerfile,
					rm=True,
					pull=True,
					tag="dll_datalab:latest"
				)
				logging.debug("Image successfully built")
				# TODO: No errors raised by cli.build. We should check this is true
				return dockerfile_str
			else:
				logging.debug("Dockerfile used: " + dockerfile)
				logging.debug("Building image as dll_datalab:latest")
				self.cli.images.build(
					path=dockerfile,
					rm=True,
					pull=True,
					tag="dll_datalab:latest"
				)
				# TODO: No errors raised by cli.build. We should check this is true
				logging.debug("Image successfully built")
				with open(dockerfile+'Dockerfile', 'r') as contents:
					return contents.read()
		except Exception as e:
			logging.error("Failed to build Image")
			return False

	def __init__(self, os_type, cli_timeout, ctrs_logfile, local_drive):
		logging.info("Instantiating DataLab API Object...")
		# Globalize passed variables
		self.cli_timeout = cli_timeout
		self.os_type = os_type
		self.ctrs_logfile = ctrs_logfile
		self.local_drive = local_drive
		self.load_containers_log()
		# Attempt import of docker library
		logging.debug("Importing Docker Python API Module...")
		try:		
			self.docker = __import__('docker')
			logging.debug("Docker Module imported")
		except Exception as e:
			raise Exception("Failed to import docker-py module")
		# Attempt to instantiate a docker client
		logging.debug("Creating Docker Client Object")
		try:
			self.cli = self.docker.DockerClient(timeout=self.cli_timeout)
			logging.debug(
				"Docker Client Object Created with Timeout = " + str(self.cli_timeout)
			)
		except Exception as e:
			raise Exception("Failed to create Docker Client Object")
		# Okay, we're ready to go!
