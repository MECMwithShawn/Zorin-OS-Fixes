"""Native control validation and restoration without touching host hardware."""
from contextlib import contextmanager
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import dbus
import hardware_controls as controls


class HardwareTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.state = Path(self.temp.name)/'profile.json'
        self.patch = patch.object(controls, 'PROFILE_STATE', self.state)
        self.patch.start(); self.addCleanup(self.patch.stop)
        self.props = Mock()
        self.power = dict(ActiveProfile='performance', Profiles=[dict(Profile=p) for p in controls.PROFILE_NAMES])
        self.props.GetAll.side_effect = lambda *_a, **_k: self.power
        self.props.Get.side_effect = lambda _interface, name, **_k: self.power[name]
        self.props.Set.side_effect = lambda _interface, name, value, **_k: self.power.update({name:value})
        self.bus = Mock()
        @contextmanager
        def connection(*_): yield self.bus
        self.connection = patch.object(controls, 'connection', connection)
        self.connection.start(); self.addCleanup(self.connection.stop)

    def test_power_snapshot_and_missing_service(self):
        with patch.object(controls.dbus, 'Interface', return_value=self.props):
            snapshot=controls.power_snapshot()
            self.assertEqual(snapshot['powerProfile'],'performance')
            self.assertTrue(snapshot['batterySaverAvailable']);self.assertEqual(len(snapshot['powerProfiles']),3)
        self.bus.get_object.side_effect=dbus.DBusException('not installed')
        self.assertFalse(controls.power_snapshot()['batterySaverAvailable'])
        self.assertEqual(controls.power_snapshot()['powerProfiles'],[])

    def test_legacy_power_service_fallback(self):
        self.bus.get_object.side_effect=[dbus.DBusException('missing modern name'),object()]
        with patch.object(controls.dbus,'Interface',return_value=self.props):
            interface,_,_=controls.power_service(self.bus)
        self.assertEqual(interface,'net.hadess.PowerProfiles')

    def test_saver_remembers_and_restores_exact_previous_mode(self):
        with patch.object(controls.dbus,'Interface',return_value=self.props):
            controls.set_power('batterySaver',True)
            self.assertEqual(self.power['ActiveProfile'],'power-saver')
            self.assertEqual(json.loads(self.state.read_text()),dict(previous='performance'))
            self.assertEqual(self.state.stat().st_mode&0o777,0o600)
            controls.set_power('batterySaver',True)
            controls.set_power('batterySaver',False)
        self.assertEqual(self.power['ActiveProfile'],'performance')
        self.assertEqual(self.props.Set.call_count,2)

    def test_saver_off_without_saved_mode_and_unavailable_previous(self):
        self.power['ActiveProfile']='power-saver'
        self.power['Profiles']=[dict(Profile=p) for p in ('power-saver','balanced')]
        self.state.write_text('{"previous":"performance"}')
        with patch.object(controls.dbus,'Interface',return_value=self.props):controls.set_power('batterySaver',False)
        self.assertEqual(self.power['ActiveProfile'],'balanced')

    def test_profile_selection_and_inhibited_or_unsupported_mode(self):
        with patch.object(controls.dbus,'Interface',return_value=self.props):
            controls.set_power('powerProfile','balanced')
            self.assertEqual(self.power['ActiveProfile'],'balanced')
            self.power['PerformanceInhibited']='lap-detected'
            with self.assertRaises(ValueError):controls.set_power('powerProfile','performance')
            self.power['Profiles']=[dict(Profile='balanced')]
            with self.assertRaises(ValueError):controls.set_power('batterySaver',True)
        self.assertEqual(self.props.Set.call_count,1)

    def test_invalid_values_never_reach_services(self):
        for name,value in (('batterySaver',1),('powerProfile','turbo'),('powerProfile',False),('shell','echo bad')):
            with self.assertRaises(ValueError):controls.set_power(name,value)
        with self.assertRaises(ValueError):controls.set_airplane('false')
        with self.assertRaises(ValueError):controls.connect_bluetooth(None,True)
        self.bus.get_object.assert_not_called()

    def test_airplane_confirmation_hardware_lock_and_no_radio(self):
        self.power=dict(HasAirplaneMode=True,HardwareAirplaneMode=False,AirplaneMode=False)
        with patch.object(controls.dbus,'Interface',return_value=self.props):
            self.assertTrue(controls.airplane_snapshot()['airplaneAvailable'])
            controls.set_airplane(True);self.assertTrue(self.power['AirplaneMode'])
            controls.set_airplane(False);self.assertFalse(self.power['AirplaneMode'])
            self.power['HardwareAirplaneMode']=True
            self.assertTrue(controls.airplane_snapshot()['airplaneBlocked'])
            with self.assertRaises(ValueError):controls.set_airplane(False)
            self.power.update(HardwareAirplaneMode=False,HasAirplaneMode=False)
            with self.assertRaises(ValueError):controls.set_airplane(True)
        self.assertEqual(self.props.Set.call_count,2)

    def test_unconfirmed_change_and_service_rejection_surface_errors(self):
        with patch.object(controls.time,'monotonic',side_effect=[0,4]):
            with self.assertRaises(RuntimeError):controls.wait_property(self.props,'interface','value',True)
        self.props.Set.side_effect=dbus.DBusException('Not authorized')
        with patch.object(controls.dbus,'Interface',return_value=self.props):
            with self.assertRaises(dbus.DBusException):controls.set_power('batterySaver',True)

    def devices(self):
        return {'/org/bluez/hci0':{'org.bluez.Adapter1':{'Powered':True}},
                '/org/bluez/hci0/dev_AA':{'org.bluez.Device1':dict(Paired=True,Connected=False,Adapter='/org/bluez/hci0',Alias='Headphones',Icon='audio-headphones'),'org.bluez.Battery1':{'Percentage':78}},
                '/org/bluez/hci0/dev_BB':{'org.bluez.Device1':dict(Paired=True,Connected=True,Adapter='/org/bluez/hci0',Alias='Keyboard')},
                '/org/bluez/hci0/dev_CC':{'org.bluez.Device1':dict(Paired=False,Connected=False,Alias='Unpaired')}}

    def test_bluetooth_groups_battery_and_absent_adapter(self):
        objects=self.devices();devices=controls.bluetooth_snapshot(objects)
        self.assertEqual([d['name'] for d in devices],['Keyboard','Headphones'])
        self.assertEqual(devices[1]['battery'],78)
        del objects['/org/bluez/hci0']
        self.assertTrue(all(not d['available'] for d in controls.bluetooth_snapshot(objects)))

    def test_bluetooth_connect_disconnect_revalidate_pairing_and_status(self):
        objects=self.devices();manager=Mock();manager.GetManagedObjects.return_value=objects
        device=Mock();properties=Mock();info=objects['/org/bluez/hci0/dev_AA']['org.bluez.Device1']
        device.Connect.side_effect=lambda **_:info.update(Connected=True)
        device.Disconnect.side_effect=lambda **_:info.update(Connected=False)
        properties.Get.side_effect=lambda *_a,**_k:info['Connected']
        def interface(_obj,name):return manager if name.endswith('ObjectManager') else properties if name==controls.PROPERTIES else device
        with patch.object(controls.dbus,'Interface',side_effect=interface):
            controls.connect_bluetooth('/org/bluez/hci0/dev_AA',True)
            controls.connect_bluetooth('/org/bluez/hci0/dev_AA',False)
            for ident in ('/org/bluez/hci0/dev_CC','/arbitrary','/org/bluez/hci0/removed'):
                with self.assertRaises(ValueError):controls.connect_bluetooth(ident,True)
            info['Blocked']=True
            with self.assertRaises(ValueError):controls.connect_bluetooth('/org/bluez/hci0/dev_AA',True)
        device.Connect.assert_called_once_with(timeout=15)
        device.Disconnect.assert_called_once_with(timeout=10)


if __name__=='__main__':unittest.main()
