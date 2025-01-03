#!/usr/bin/env python

import os
import subprocess
import tempfile
import yaml

from collections.abc import Mapping

from ansible.errors import AnsibleError, AnsibleParserError
from ansible.module_utils.basic import json_dict_bytes_to_unicode
from ansible.module_utils.common.text.converters import to_native, to_text
from ansible.plugins.inventory import BaseInventoryPlugin
from ansible.utils.display import Display

display = Display()

ps_script = """#!/usr/bin/env powershell.exe
    $GroupName = '{0}'
    $vms = Get-VM |
        Where-Object { $_.State -eq 'Running' -And $_.Groups.Name -eq $GroupName } |
        Add-Member -Passthru -MemberType ScriptProperty -Name Hostname -Value {
            $this.VMName.SubString($GroupName.Length + 1)
        }

    $groups = $vms.Groups.Name | Sort-Object -Unique

    $hostvars = @{}
    foreach ($vmhost in $vms) {
        $hostvars.Add($vmhost.Hostname, [PSCustomObject]@{
            ansible_host = $vmhost.NetworkAdapters[0].IPAddresses[0]
        })
    }

    $result = @{
        _meta = @{
            hostvars = $hostvars
        }
    }

    foreach ($group in $groups) {
        $members = $vms |
            Where-Object { $_.Groups.Name -eq $group } |
            Select-Object -ExpandProperty Hostname
        $result.Add($group, @{hosts = @($members)})
    }

    $result | ConvertTo-Json -Depth 5
"""

class InventoryModule(BaseInventoryPlugin):

    NAME = 'vm'

    def __init__(self):

        super(InventoryModule, self).__init__()

        self._hosts = set()

    def verify_file(self, path):
        ''' return true/false if this is possibly a valid file for this plugin to consume '''
        if super(InventoryModule, self).verify_file(path):
            if path.endswith(('hyperv.yaml', 'hyperv.yml')):
                return True

            try:
                with open(path, 'r') as stream:
                    yaml_data = yaml.safe_load(stream)
            except Exception as e:
                print(e)
                raise AnsibleParserError(e)

            if ('plugin' in yaml_data and yaml_data['plugin'] == 'ahaydon.hyperv.vm'):
                return True
            else:
                return False

    def parse(self, inventory, loader, path, cache=True):
        super(InventoryModule, self).parse(inventory, loader, path, cache)

        try:
            display.vv('Looking up temp path')
            sp = subprocess.Popen(["powershell.exe", "-NoProfile", "-NoLogo", "-ExecutionPolicy", "Unrestricted", "$env:TEMP"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except OSError as e:
            raise AnsibleParserError("problem looking up temp var (%s)" % (to_native(e)))
        (stdout, stderr) = sp.communicate()
        display.vv('TEMP:')
        tmpvar = to_text(stdout, errors="strict").rstrip("\r\n")
        display.vvv(str(bytes(tmpvar, "utf-8")))

        try:
            display.vv('Resolving TEMP path')
            sp = subprocess.Popen(["wslpath", tmpvar], stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="UTF8")
        except OSError as e:
            raise AnsibleParserError("problem resolving temp path (%s)" % (to_native(e)))
        (stdout, stderr) = sp.communicate()
        tmpdir = to_text(stdout, errors="strict").rstrip("\n")
        display.vvv(str(bytes(tmpdir, "utf-8")))

        display.vv('Creating temp script file')
        fd, tmppath = tempfile.mkstemp(dir=tmpdir, suffix=".ps1")

        try:
            with os.fdopen(fd, "w") as tmp:
                tmp.write(ps_script.replace('{0}', os.path.basename(os.getcwd()).replace('-', '_')))
            display.vv('Making script executable')
            os.chmod(tmppath, 0o755)
        except Exception as e:
            raise AnsibleError(to_native(e))
        finally:
            cmd = os.path.realpath(os.path.relpath(tmppath, os.getcwd()))

        try:
            try:
                display.vv('Resolving WSL path')
                sp = subprocess.Popen(["wslpath", "-w", cmd], stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="UTF8")
            except OSError as e:
                raise AnsibleParserError("problem resolving script path %s (%s)" % (' '.join(cmd), to_native(e)))
            (stdout, stderr) = sp.communicate()
            cmd = str(stdout)

            try:
                display.vv('Collecting inventory')
                sp = subprocess.Popen(["powershell.exe", "-NoProfile", "-NoLogo", "-ExecutionPolicy", "Unrestricted", cmd], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            except OSError as e:
                raise AnsibleParserError("problem running %s (%s)" % (' '.join(cmd), to_native(e)))
            (stdout, stderr) = sp.communicate()
            display.vv('Collection complete')
            display.vvv(str(stdout))

            path = to_native(path)
            err = to_native(stderr or "")

            if err and not err.endswith('\n'):
                err += '\n'

            if sp.returncode != 0:
                raise AnsibleError("Inventory script (%s) had an execution error: %s " % (path, err))

            try:
                data = to_text(stdout, errors="strict")
            except Exception as e:
                raise AnsibleError("Inventory {0} contained characters that cannot be interpreted as UTF-8: {1}".format(path, to_native(e)))

            try:
                processed = self.loader.load(data, json_only=True)
            except Exception as e:
                raise AnsibleError("failed to parse executable inventory script results from {0}: {1}\n{2}".format(path, to_native(e), err))

            if stderr and self.get_option('always_show_stderr'):
                self.display.error(msg=to_text(err))

            if not isinstance(processed, Mapping):
                raise AnsibleError("failed to parse executable inventory script results from {0}: needs to be a json dict\n{1}".format(path, err))

            group = None
            data_from_meta = None

            for (group, gdata) in processed.items():
                if group == '_meta':
                    if 'hostvars' in gdata:
                        data_from_meta = gdata['hostvars']
                else:
                    self._parse_group(group.replace('-', '_'), gdata)

            for host in self._hosts:
                got = {}
                if data_from_meta is None:
                    got = self.get_host_variables(path, host)
                else:
                    try:
                        got = data_from_meta.get(host, {})
                    except AttributeError as e:
                        raise AnsibleError("Improperly formatted host information for %s: %s" % (host, to_native(e)), orig_exc=e)

                self._populate_host_vars([host], got)

        except Exception as e:
            raise AnsibleParserError(to_native(e))
        finally:
            os.remove(tmppath)

    def _parse_group(self, group, data):

        group = self.inventory.add_group(group)

        if not isinstance(data, dict):
            data = {'hosts': data}
        elif not any(k in data for k in ('hosts', 'vars', 'children')):
            data = {'hosts': [group], 'vars': data}

        if 'hosts' in data:
            if not isinstance(data['hosts'], list):
                raise AnsibleError("You defined a group '%s' with bad data for the host list:\n %s" % (group, data))

            for hostname in data['hosts']:
                self._hosts.add(hostname)
                self.inventory.add_host(hostname, group)
                self.inventory.set_variable(hostname, 'ansible_connection', 'psrp')
                self.inventory.set_variable(hostname, 'ansible_psrp_auth', 'basic')
                self.inventory.set_variable(hostname, 'ansible_psrp_cert_validation', 'ignore')

        if 'vars' in data:
            if not isinstance(data['vars'], dict):
                raise AnsibleError("You defined a group '%s' with bad data for variables:\n %s" % (group, data))

            for k, v in data['vars'].items():
                self.inventory.set_variable(group, k, v)

        if group != '_meta' and isinstance(data, dict) and 'children' in data:
            for child_name in data['children']:
                child_name = self.inventory.add_group(child_name)
                self.inventory.add_child(group, child_name)

    def get_host_variables(self, path, host):
        """ Runs <script> --host <hostname>, to determine additional host variables """

        cmd = [path, "--host", host]
        try:
            sp = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except OSError as e:
            raise AnsibleError("problem running %s (%s)" % (' '.join(cmd), e))
        (out, stderr) = sp.communicate()

        if sp.returncode != 0:
            raise AnsibleError("Inventory script (%s) had an execution error: %s" % (path, to_native(stderr)))

        if out.strip() == '':
            return {}
        try:
            return json_dict_bytes_to_unicode(self.loader.load(out, file_name=path))
        except ValueError:
            raise AnsibleError("could not parse post variable response: %s, %s" % (cmd, out))
