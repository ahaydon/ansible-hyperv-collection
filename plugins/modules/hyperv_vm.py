#!/usr/bin/python
# -*- coding: utf-8 -*-

# This file is part of Ansible
#
# Ansible is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Ansible is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Ansible.  If not, see <http://www.gnu.org/licenses/>.

# this is a windows documentation stub. actual code lives in the .ps1
# file of the same name

from typing import Any


DOCUMENTATION = """
---
module: hyperv_vm
version_added: "2.4"
short_description: Adds, deletes and performs power functions on Hyper-V VM's.
description:
    - Adds, deletes and performs power functions on Hyper-V VM's.
options:
  name:
    description:
      - Name of VM
    required: true
  state:
    description:
      - State of VM
    required: false
    choices:
      - present
      - absent
	  - running
	  - stopped
      - poweroff
    default: present
  cpu:
    description:
      - Sets the number of vCPUs to assign to the VM
    required: false
    default: 1
  memory:
    description:
      - Sets the amount of memory for the VM
    required: false
    default: 512MB
  generation:
    description:
      - Specifies the generation of the VM
    required: false
    default: 2
  network_switch:
    description:
      - Specifies a network adapter for the VM
    required: false
  vhd_path:
    description:
      - Specify path of VHD/VHDX file for VM
	  - If the file exists it will be attached, if not then a new one will be created
    require: false
  vhd_parent_path:
    description:
      - Specifies the path of a parent image for a differencing disk
    required: false
  vhd_size_bytes:
    description:
      - Specifies the size of the disk to create
    required: false
    default: 40GB
  group_names:
    description:
      - Specifies a list of groups the VM should be added to
    required: false
    default: []
"""

EXAMPLES = """
  # Create VM
  hyperv_vm:
    name: Test

  # Delete a VM
  hyperv_vm:
    name: Test
	state: absent

  # Create VM with 256MB memory
  hyperv_vm:
    name: Test
	memory: 256MB

  # Create generation 1 VM with 256MB memory and a network adapter
  hyperv_vm:
    name: Test
    generation: 1
    memory: 256MB
    network_switch: WAN1
"""

ANSIBLE_METADATA: dict[str, Any] = {
    "status": ["preview"],
    "supported_by": "community",
    "metadata_version": "1.1",
}
