#!/usr/bin/env python3

# Copyright 2019 Canonical Ltd.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Encapsulate Ceilometer testing."""

import copy
import logging

import ceilometerclient.v2.client as ceilo_client
import zaza.openstack.charm_tests.test_utils as test_utils
import zaza.openstack.utilities.openstack as openstack_utils


class CeilometerTest(test_utils.OpenStackBaseTest):
    """Encapsulate Ceilometer tests."""

    CONF_FILE = '/etc/ceilometer/ceilometer.conf'

    XENIAL_PIKE = openstack_utils.get_os_release('xenial_pike')
    XENIAL_OCATA = openstack_utils.get_os_release('xenial_ocata')
    XENIAL_NEWTON = openstack_utils.get_os_release('xenial_newton')
    XENIAL_MITAKA = openstack_utils.get_os_release('xenial_mitaka')
    TRUSTY_MITAKA = openstack_utils.get_os_release('trusty_mitaka')

    @classmethod
    def setUpClass(cls):
        """Run class setup for running Ceilometer tests."""
        super(CeilometerTest, cls).setUpClass()
        cls.current_release = openstack_utils.get_os_release()

    @property
    def services(self):
        """Return a list of services for the selected OpenStack release."""
        services = []

        if self.application_name == 'ceilometer-agent':
            if self.current_release <= CeilometerTest.XENIAL_MITAKA:
                services.append('ceilometer-polling')
            else:
                services.append('ceilometer-polling: AgentManager worker(0)')
            return services

        # Note: disabling ceilometer-polling and ceilometer-agent-central due
        # to bug 1846390: https://bugs.launchpad.net/bugs/1846390
        if self.current_release >= CeilometerTest.XENIAL_PIKE:
            # services.append('ceilometer-polling: AgentManager worker(0)')
            services.append('ceilometer-agent-notification: '
                            'NotificationService worker(0)')
        elif self.current_release >= CeilometerTest.XENIAL_OCATA:
            services.append('ceilometer-collector: CollectorService worker(0)')
            # services.append('ceilometer-polling: AgentManager worker(0)')
            services.append('ceilometer-agent-notification: '
                            'NotificationService worker(0)')
            services.append('apache2')
        elif self.current_release >= CeilometerTest.XENIAL_NEWTON:
            services.append('ceilometer-collector - CollectorService(0)')
            # services.append('ceilometer-polling - AgentManager(0)')
            services.append('ceilometer-agent-notification - '
                            'NotificationService(0)')
            services.append('ceilometer-api')
        else:
            services.append('ceilometer-collector')
            services.append('ceilometer-api')
            services.append('ceilometer-agent-notification')

            if self.current_release < CeilometerTest.TRUSTY_MITAKA:
                services.append('ceilometer-alarm-notifier')
                services.append('ceilometer-alarm-evaluator')

        return services

    @property
    def restartable_services(self):
        """Return a list of services that are known to be restartable.

        For the selected OpenStack release these services are known to be able
        to be stopped and started with no issues.
        """
        # Due to Bug #1861321 ceilometer-collector does not reliably
        # restart.
        _services = copy.deepcopy(self.services)
        if self.current_release <= CeilometerTest.TRUSTY_MITAKA:
            try:
                _services.remove('ceilometer-collector')
            except ValueError:
                pass
        return _services

    def test_400_api_connection(self):
        """Simple api calls to check service is up and responding."""
        if self.current_release >= CeilometerTest.XENIAL_OCATA:
            logging.info('Skipping API checks as ceilometer api has been '
                         'removed')
            return

        logging.info('Instantiating ceilometer client...')
        ceil = ceilo_client.Client(
            session=openstack_utils.get_overcloud_keystone_session()
        )

        logging.info('Checking api functionality...')
        assert ceil.samples.list() == []
        assert ceil.meters.list() == []

    def test_900_restart_on_config_change(self):
        """Checking restart happens on config change."""
        config_name = 'debug'

        if self.application_name == 'ceilometer-agent':
            config_name = 'use-internal-endpoints'

        # Expected default and alternate values
        current_value = openstack_utils.get_application_config_option(
            self.application_name, config_name
        )
        assert type(current_value) == bool
        new_value = not current_value

        # Convert bool to str
        current_value = str(current_value)
        new_value = str(new_value)

        set_default = {config_name: current_value}
        set_alternate = {config_name: new_value}

        default_entry = {'DEFAULT': {'debug': [current_value]}}
        alternate_entry = {'DEFAULT': {'debug': [new_value]}}

        if self.application_name == 'ceilometer-agent':
            default_entry = None
            alternate_entry = {
                'service_credentials': {'interface': ['internalURL']}
            }

        logging.info('changing config: {}'.format(set_alternate))
        self.restart_on_changed(
            CeilometerTest.CONF_FILE,
            set_default,
            set_alternate,
            default_entry,
            alternate_entry,
            self.restartable_services)

    def test_901_pause_resume(self):
        """Run pause and resume tests.

        Pause service and check services are stopped then resume and check
        they are started.
        """
        if self.application_name == 'ceilometer-agent':
            logging.info("ceilometer-agent doesn't have pause/resume actions "
                         "anymore, skipping")
            return

        with self.pause_resume(self.restartable_services):
            logging.info("Testing pause and resume")
