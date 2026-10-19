"""Discovery clutter and identity boundaries; no host radio changes."""
import unittest
from pathlib import Path
from unittest.mock import Mock,patch
import dbus
from bluetooth_pairing import nearby_groups,PairingAgent,Rejected,PairingSession

class PairingTests(unittest.TestCase):
    def objects(self):
        objects={'/adapter':{'org.bluez.Adapter1':{'Powered':True}}}
        for i in range(84):
            objects['/adapter/dev_'+str(i)]={'org.bluez.Device1':dict(Name='Omni',Address=f'AA:BB:CC:DD:EE:{i:02X}',Adapter='/adapter',RSSI=-30-i)}
        objects['/adapter/airpods']={'org.bluez.Device1':dict(Alias="Shawn's AirPods",Address='11:22:33:44:55:66',Adapter='/adapter',RSSI=-40)}
        return objects
    def test_repeated_names_collapse_without_merging_identity(self):
        groups=nearby_groups(self.objects())
        self.assertEqual(len(groups),2)
        omni=next(g for g in groups if g['name']=='Omni')
        self.assertEqual(len(omni['devices']),84)
        self.assertEqual(len({d['id'] for d in omni['devices']}),84)
        self.assertGreater(omni['devices'][0]['signal'],omni['devices'][-1]['signal'])
    def test_name_address_search_and_paired_blocked_filter(self):
        objects=self.objects()
        self.assertEqual(nearby_groups(objects,'AIRPODS')[0]['devices'][0]['id'],'/adapter/airpods')
        self.assertEqual(len(nearby_groups(objects,'11:22:33')[0]['devices']),1)
        for prop,value in [('Paired',True),('Blocked',True),('Connectable',dbus.Boolean(False))]:
            with self.subTest(prop=prop):
                objects=self.objects();objects['/adapter/airpods']['org.bluez.Device1'][prop]=value
                self.assertEqual(nearby_groups(objects,'AirPods'),[])
        objects=self.objects();objects['/adapter']['org.bluez.Adapter1']['Powered']=False
        self.assertEqual(nearby_groups(objects),[])
    def test_unknown_names_group_and_untrusted_names_remain_plain_text(self):
        objects=self.objects();info=objects['/adapter/airpods']['org.bluez.Device1']
        info['Alias']='11-22-33-44-55-66'
        self.assertEqual(nearby_groups(objects)[-1]['name'],'Unnamed devices')
        info['Alias']='<b>AirPods</b>'
        self.assertEqual(nearby_groups(objects,'AirPods')[0]['name'],'<b>AirPods</b>')
    def test_agent_rejects_unrequested_devices_and_other_bus_clients(self):
        agent=object.__new__(PairingAgent);agent.session=Mock(owner=':1.42',target='/expected')
        agent.check(':1.42','/expected')
        for sender,path in [(':1.99','/expected'),(':1.42','/other')]:
            with self.assertRaises(Rejected):agent.check(sender,path)
    def test_add_device_launches_the_picker(self):
        import settings_backend
        with patch.object(settings_backend.subprocess,'Popen') as launch:
            settings_backend.launch('bluetooth')
        command=launch.call_args.args[0]
        self.assertEqual(Path(command[1]).name,'bluetooth_pairing.py')
        self.assertTrue(launch.call_args.kwargs['start_new_session'])

    def test_selection_waits_for_an_inflight_refresh(self):
        session=object.__new__(PairingSession)
        session.closed=False;session.pending=True;session.waiters=[]
        callback=Mock();session.refresh(callback)
        self.assertEqual(session.waiters,[callback]);callback.assert_not_called()

if __name__=='__main__':unittest.main()
