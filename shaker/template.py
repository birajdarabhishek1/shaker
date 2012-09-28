#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Handle the templates to configure user-data.
"""
import os
import re
from jinja2 import Environment
from jinja2 import FileSystemLoader

from shaker import __version__

import shaker.log
LOG = shaker.log.getLogger(__name__)

CLOUD_INIT_PREFIX = 'cloud-init'
USER_SCRIPT_PREFIX = 'user-script'


class UserData(object):
    def __init__(self, config):
        self.config = config
        self.config.update({'version': __version__})
        self.template_dir = self.get_template_dir(self.config['config_dir'])
        self.env = self.get_jinja_env()
        minion_template = re.sub('\n\n+', '\n\n', self.render_template('minion_template', default_contents=MINION_TEMPLATE))
        self.config['rendered_minion_template'] = minion_template
        self.user_script = re.sub('\n\n+', '\n\n', self.render_template('user_data_template', default_contents=USER_SCRIPT))
        self.cloud_init = re.sub('\n\n+', '\n\n', self.render_template('cloud_init_template', default_contents=CLOUD_INIT))

    def get_jinja_env(self):
        ## Using '/' in loader allows to check for absolute paths.
        loader = FileSystemLoader([os.getcwd(), self.template_dir, '/'])
        env = Environment(loader=loader)
        return env

    def render_template(self, template_arg, default_contents=None):
        """
        Retrieve rendered template text from file.
        """
        prefixes = {
            'cloud_init_template': CLOUD_INIT_PREFIX,
            'user_data_template': USER_SCRIPT_PREFIX,
            'minion_template': 'minion-template'
        }
        prefix = prefixes[template_arg]

        if self.config[template_arg] == None:
            template_name = "%s.%s" % (prefix, __version__)
            template_path = os.path.join(self.template_dir, template_name)
            ## Create from default if it doesn't exist.
            if not os.path.isfile(template_path):
                template_file = open(template_path, 'w')
                template_file.write(default_contents)
                template_file.close()
        else:
            template_name = self.config[template_arg]

        return self.env.get_template(template_name).render(self.config)

    def get_template_dir(self, config_dir):
        """Return the template directory name, creating the
        directory if absent (and populating with boilerplate).
        """
        template_dir = os.path.join(config_dir, 'templates')
        if not os.path.isdir(template_dir):
            os.makedirs(template_dir)
        return template_dir


CLOUD_INIT = """#cloud-config
# Shaker version: {{ version }}
{% if salt_master %}
{% if not ec2_distro in ['lucid', 'maverick', 'natty'] %}
apt_sources:
  - source: "ppa:saltstack/salt"

apt_upgrade: true
{% endif %}
{% endif %}

{% if ssh_import %}
ssh_import_id: [{{ ssh_import }}]
{% endif %}

{% if hostname %}
hostname: {{ hostname }}
{% if domain %}
fqdn: {{ hostname }}.{{ domain }}
{% endif %}
{% endif %}

{{ rendered_minion_template }}
"""

USER_SCRIPT = """#!/bin/sh
# Shaker version: {{ version }}
{% if timezone %}
# set timezone
echo "{{ timezone }}" | tee /etc/timezone
dpkg-reconfigure --frontend noninteractive tzdata
restart cron
{% endif %}

{% if domain and hostname %}
sed -i "s/127.0.0.1 ubuntu/127.0.0.1 localhost {{ hostname }}.{{ domain }} {{ hostname }}/" /etc/hosts
# temp work-around for cloudinit bug: https://bugs.launchpad.net/cloud-init/
echo "127.0.0.1 localhost {{ hostname }}.{{ domain }} {{ hostname }}" >> /etc/hosts
{% elif hostname %}
  hostname: {{ hostname }}
{% endif %}

{% if ssh_port and ssh_port != '22' %}
# change ssh port 22 to non-standard port and restart sshd
sed -i "s/^Port 22$/Port {{ ssh_port }}/" /etc/ssh/sshd_config
/etc/init.d/ssh restart
{% endif %}

{% if sudouser %}
# create new user with sudo privileges
useradd -m -s /bin/bash {{ sudouser }}
{% if ssh_import %}cp -rp /home/ubuntu/.ssh /home/{{ sudouser }}/.ssh
chown -R {{ sudouser }}:{{ sudouser }} /home/{{ sudouser }}/.ssh
{% endif %}
echo "{{ sudouser }} ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers
{% endif %}

{% if size and root_device %}
# resize the filesystem to use specified space
resize2fs {{ root_device }}
{% endif %}

{% if salt_master %}
# Install salt-minion and run as daemon

{% if ec2_distro in ['lucid', 'maverick'] %}
aptitude -y install python-software-properties && add-apt-repository ppa:chris-lea/libpgm && add-apt-repository ppa:chris-lea/zeromq && add-apt-repository ppa:saltstack/salt && aptitude update
{% endif %}

#apt-get -y install salt-minion
#service salt-minion restart
{% endif %}
"""


MINION_TEMPLATE = """
salt_minion:
  # conf contains all the directives to be assigned in /etc/salt/minion.

  conf:
    # Set the location of the salt master server, if the master server cannot be
    # resolved, then the minion will fail to start.
    master: {{ salt_master }}

    {% if salt_id %}
    id: {{ salt_id }}
    {% else %}
    #id:
    {% endif %}

{% if formatted_public_key %}
  # Salt keys are manually generated by: salt-key --gen-keys=GEN_KEYS
  # where GEN_KEYS is the name of the keypair, e.g. 'minion'.  The keypair
  # will be copied to /etc/salt/pki on the minion instance.

  public_key: |
{{ formatted_public_key }}
{% endif %}

{% if formatted_private_key %}
  private_key: |
{{ formatted_private_key }}
{% endif %}
"""