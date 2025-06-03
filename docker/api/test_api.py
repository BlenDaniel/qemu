import unittest
import json
from unittest.mock import Mock, patch, MagicMock
import sys
import os
import subprocess

# Add the current directory to the path so we can import app
sys.path.insert(0, os.path.dirname(__file__))

class TestUnifiedEmulatorAPI(unittest.TestCase):
    
    def setUp(self):
        """Set up test fixtures"""
        # Mock Docker before importing app
        with patch('docker.from_env'):
            from app import app, sessions, generate_device_id
            self.app = app
            self.sessions = sessions
            self.generate_device_id = generate_device_id
        
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()
        # Clear sessions before each test
        self.sessions.clear()
    
    def tearDown(self):
        """Clean up after tests"""
        self.sessions.clear()
    
    def test_generate_device_id(self):
        """Test device ID generation"""
        device_id = self.generate_device_id()
        self.assertEqual(len(device_id), 8)
        self.assertTrue(device_id.isalnum())
        self.assertTrue(device_id.islower())
    
    def test_generate_unique_device_ids(self):
        """Test that device IDs are unique"""
        ids = [self.generate_device_id() for _ in range(100)]
        self.assertEqual(len(ids), len(set(ids)))
    
    def test_index_route(self):
        """Test that the main page renders correctly"""
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Android Emulator Manager', response.data)
        # Check for key UI elements
        self.assertIn(b'Create New Emulator', response.data)
        self.assertIn(b'ADB Quick Actions', response.data)
        self.assertIn(b'Running Emulators', response.data)
        # Check for VNC-related UI elements
        self.assertIn(b'VNC Screen', response.data)
        self.assertIn(b'Live View', response.data)
    
    @patch('app.get_docker_client')
    @patch('app.run_adb_command')
    @patch('app.kill_all_adb_processes')
    @patch('app.wait_for_device')
    def test_create_emulator_android_11_with_vnc(self, mock_wait_for_device, mock_kill_adb, mock_adb_command, mock_get_docker):
        """Test creating Android 11 emulator with VNC support"""
        # Mock Docker client and container
        mock_client = Mock()
        mock_container = Mock()
        mock_container.attrs = {
            'NetworkSettings': {
                'Ports': {
                    '5554/tcp': [{'HostPort': '5334'}],
                    '5555/tcp': [{'HostPort': '5556'}],
                    '5037/tcp': [{'HostPort': '5038'}],
                    '5900/tcp': [{'HostPort': '5901'}]  # VNC port
                }
            }
        }
        mock_client.containers.run.return_value = mock_container
        mock_get_docker.return_value = mock_client
        
        # Mock ADB commands and wait functions
        mock_adb_command.return_value = {"success": True, "output": "device"}
        mock_wait_for_device.return_value = "device"
        
        # Test data
        test_data = {
            'android_version': '11',
            'map_adb_server': True
        }
        
        response = self.client.post('/api/emulators', 
                                  data=json.dumps(test_data),
                                  content_type='application/json')
        
        self.assertEqual(response.status_code, 201)
        data = json.loads(response.data)
        
        # Verify response structure includes VNC
        self.assertIn('id', data)
        self.assertIn('device_id', data)
        self.assertIn('android_version', data)
        self.assertEqual(data['android_version'], '11')
        self.assertIn('ports', data)
        self.assertIn('vnc', data['ports'])
        self.assertEqual(data['ports']['vnc'], '5901')
        
        # Verify session was created with VNC port
        self.assertEqual(len(self.sessions), 1)
        session = list(self.sessions.values())[0]
        self.assertEqual(session['vnc_port'], '5901')
    
    @patch('app.get_docker_client')
    @patch('app.run_adb_command')
    @patch('app.kill_all_adb_processes')
    @patch('app.wait_for_device')
    def test_create_emulator_android_14_with_vnc(self, mock_wait_for_device, mock_kill_adb, mock_adb_command, mock_get_docker):
        """Test creating Android 14 emulator with VNC support"""
        # Mock Docker client and container
        mock_client = Mock()
        mock_container = Mock()
        mock_container.attrs = {
            'NetworkSettings': {
                'Ports': {
                    '5554/tcp': [{'HostPort': '5334'}],
                    '5555/tcp': [{'HostPort': '5556'}],
                    '5037/tcp': [{'HostPort': '5038'}],
                    '5900/tcp': [{'HostPort': '5902'}]  # VNC port
                }
            }
        }
        mock_client.containers.run.return_value = mock_container
        mock_get_docker.return_value = mock_client
        
        # Mock ADB commands and wait functions
        mock_adb_command.return_value = {"success": True, "output": "device"}
        mock_wait_for_device.return_value = "device"
        
        # Test data
        test_data = {
            'android_version': '14',
            'map_adb_server': True
        }
        
        response = self.client.post('/api/emulators', 
                                  data=json.dumps(test_data),
                                  content_type='application/json')
        
        self.assertEqual(response.status_code, 201)
        data = json.loads(response.data)
        
        # Verify Android 14 specific data with VNC
        self.assertEqual(data['android_version'], '14')
        self.assertEqual(data['ports']['vnc'], '5902')
        
        # Verify session was created with correct version and VNC
        session = list(self.sessions.values())[0]
        self.assertEqual(session['android_version'], '14')
        self.assertEqual(session['vnc_port'], '5902')
    
    @patch('app.get_docker_client')
    @patch('app.run_adb_command')
    @patch('app.kill_all_adb_processes')
    @patch('app.wait_for_device')
    def test_create_emulator_defaults_to_android_11(self, mock_wait_for_device, mock_kill_adb, mock_adb_command, mock_get_docker):
        """Test that invalid Android versions default to 11"""
        # Mock Docker client and container
        mock_client = Mock()
        mock_container = Mock()
        mock_container.attrs = {
            'NetworkSettings': {
                'Ports': {
                    '5554/tcp': [{'HostPort': '5334'}],
                    '5555/tcp': [{'HostPort': '5556'}],
                    '5037/tcp': [{'HostPort': '5038'}],
                    '5900/tcp': [{'HostPort': '5903'}]
                }
            }
        }
        mock_client.containers.run.return_value = mock_container
        mock_get_docker.return_value = mock_client
        
        # Mock ADB commands and wait functions
        mock_adb_command.return_value = {"success": True, "output": "device"}
        mock_wait_for_device.return_value = "device"
        
        # Test data with invalid version
        test_data = {
            'android_version': '99',  # Invalid version
            'map_adb_server': True
        }
        
        response = self.client.post('/api/emulators', 
                                  data=json.dumps(test_data),
                                  content_type='application/json')
        
        self.assertEqual(response.status_code, 201)
        data = json.loads(response.data)
        
        # Should default to Android 11
        self.assertEqual(data['android_version'], '11')
    
    def test_vnc_viewer_endpoint(self):
        """Test VNC viewer endpoint"""
        # Mock session with VNC port
        mock_container = Mock()
        mock_container.attrs = {
            'NetworkSettings': {
                'Ports': {
                    '5554/tcp': [{'HostPort': '5334'}],
                    '5555/tcp': [{'HostPort': '5556'}],
                    '5037/tcp': [{'HostPort': '5038'}],
                    '5900/tcp': [{'HostPort': '5904'}]
                }
            }
        }
        
        self.sessions['test-vnc-id'] = {
            'container': mock_container,
            'device_port': '5334',
            'device_id': 'testdev',
            'android_version': '11',
            'vnc_port': '5904'
        }
        
        response = self.client.get('/vnc/test-vnc-id')
        self.assertEqual(response.status_code, 200)
        # Check if VNC viewer HTML is returned
        self.assertIn(b'Android Emulator Screen', response.data)
        self.assertIn(b'testdev', response.data)
    
    def test_vnc_viewer_not_found(self):
        """Test VNC viewer for non-existent emulator"""
        response = self.client.get('/vnc/nonexistent')
        self.assertEqual(response.status_code, 404)
    
    def test_vnc_viewer_no_vnc_port(self):
        """Test VNC viewer for emulator without VNC"""
        # Mock session without VNC port
        mock_container = Mock()
        self.sessions['test-no-vnc'] = {
            'container': mock_container,
            'device_port': '5334',
            'device_id': 'testdev',
            'android_version': '11'
            # No vnc_port
        }
        
        response = self.client.get('/vnc/test-no-vnc')
        self.assertEqual(response.status_code, 404)
    
    @patch('subprocess.run')
    def test_screenshot_endpoint(self, mock_subprocess):
        """Test screenshot endpoint"""
        # Mock session
        self.sessions['test-screenshot'] = {
            'device_id': 'testdev',
            'ports': {
                'adb': '5556',
                'adb_server': '5038'
            }
        }
        
        # Mock multiple subprocess calls that the enhanced screenshot endpoint makes
        def mock_subprocess_side_effect(*args, **kwargs):
            cmd = args[0]
            mock_result = Mock()
            mock_result.returncode = 0
            
            if 'connect' in cmd:
                # ADB connect command
                mock_result.stdout = 'connected to localhost:5556'
                mock_result.stderr = b''
            elif 'devices' in cmd:
                # ADB devices command
                mock_result.stdout = 'List of devices attached\nlocalhost:5556\tdevice\n'
                mock_result.stderr = b''
            elif 'screencap' in cmd:
                # Screenshot command
                mock_result.stdout = b'fake_png_data'
                mock_result.stderr = b''
            else:
                # Default case
                mock_result.stdout = ''
                mock_result.stderr = b''
            
            return mock_result
        
        mock_subprocess.side_effect = mock_subprocess_side_effect
        
        response = self.client.get('/api/emulators/test-screenshot/screenshot')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data['success'])
        self.assertIn('screenshot', data)
        self.assertTrue(data['screenshot'].startswith('data:image/png;base64,'))
    
    @patch('subprocess.run')
    def test_screenshot_failure(self, mock_subprocess):
        """Test screenshot endpoint failure"""
        # Mock session
        self.sessions['test-screenshot-fail'] = {
            'device_id': 'testdev',
            'ports': {
                'adb': '5556',
                'adb_server': '5038'
            }
        }
        
        # Mock failed screenshot
        mock_subprocess.side_effect = subprocess.CalledProcessError(1, 'adb', stderr=b'device not found')
        
        response = self.client.get('/api/emulators/test-screenshot-fail/screenshot')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertFalse(data['success'])
        self.assertIn('error', data)
    
    def test_adb_connect_endpoint(self):
        """Test ADB connect endpoint"""
        test_data = {
            'adb_port': '5556',
            'adb_server_port': '5038'
        }
        
        with patch('app.run_adb_command') as mock_adb:
            mock_adb.return_value = {"success": True, "output": "connected"}
            
            response = self.client.post('/api/adb/connect',
                                      data=json.dumps(test_data),
                                      content_type='application/json')
            
            self.assertEqual(response.status_code, 200)
            data = json.loads(response.data)
            self.assertTrue(data['success'])
    
    def test_adb_devices_endpoint(self):
        """Test ADB devices endpoint"""
        with patch('app.run_adb_command') as mock_adb:
            mock_adb.return_value = {"success": True, "output": "List of devices attached\nemulator-5334\tdevice\n"}
            
            response = self.client.get('/api/adb/devices?port=5038')
            
            self.assertEqual(response.status_code, 200)
            data = json.loads(response.data)
            self.assertTrue(data['success'])
    
    def test_adb_install_endpoint(self):
        """Test APK install endpoint"""
        test_data = {
            'apk_path': '/path/to/app.apk',
            'device': 'emulator-5334',
            'adb_server_port': '5038'
        }
        
        with patch('app.run_adb_command') as mock_adb:
            mock_adb.return_value = {"success": True, "output": "Success"}
            
            response = self.client.post('/api/adb/install',
                                      data=json.dumps(test_data),
                                      content_type='application/json')
            
            self.assertEqual(response.status_code, 200)
            data = json.loads(response.data)
            self.assertTrue(data['success'])
    
    def test_adb_install_missing_apk_path(self):
        """Test APK install with missing path"""
        test_data = {
            'device': 'emulator-5334',
            'adb_server_port': '5038'
        }
        
        response = self.client.post('/api/adb/install',
                                  data=json.dumps(test_data),
                                  content_type='application/json')
        
        self.assertEqual(response.status_code, 400)
        data = json.loads(response.data)
        self.assertIn('error', data)
    
    def test_legacy_endpoints_compatibility(self):
        """Test that legacy endpoints still work"""
        # Test legacy GET emulators
        response = self.client.get('/emulators')
        self.assertEqual(response.status_code, 200)
        
        # Test legacy ADB status
        with patch('subprocess.run') as mock_subprocess:
            mock_subprocess.return_value.stdout = "List of devices attached\n"
            response = self.client.get('/adb?adb=5038')
            self.assertEqual(response.status_code, 200)
    
    def test_list_emulators_with_android_version_and_vnc(self):
        """Test listing emulators includes Android version and VNC port"""
        # Mock container
        mock_container = Mock()
        mock_container.attrs = {
            'NetworkSettings': {
                'Ports': {
                    '5554/tcp': [{'HostPort': '5334'}],
                    '5555/tcp': [{'HostPort': '5556'}],
                    '5037/tcp': [{'HostPort': '5038'}],
                    '5900/tcp': [{'HostPort': '5906'}]
                }
            }
        }
        mock_container.status = 'running'
        
        # Add mock session with Android version and VNC
        self.sessions['test-id'] = {
            'container': mock_container,
            'device_port': '5334',
            'device_id': 'test123',
            'android_version': '14',
            'has_external_adb_server': True,
            'vnc_port': '5906',
            'adb_commands': {
                'connect': 'adb connect localhost:5556',
                'server': 'adb -P 5038 devices',
                'set_server_unix': 'export ANDROID_ADB_SERVER_PORT=5038',
                'set_server_windows': 'set ANDROID_ADB_SERVER_PORT=5038',
                'kill_and_restart_server': 'adb kill-server && adb -P 5038 start-server'
            }
        }
        
        response = self.client.get('/api/emulators')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        
        self.assertIn('test-id', data)
        emulator = data['test-id']
        self.assertEqual(emulator['device_id'], 'test123')
        self.assertEqual(emulator['android_version'], '14')
        self.assertEqual(emulator['status'], 'running')
        self.assertEqual(emulator['ports']['vnc'], '5906')
    
    @patch('subprocess.run')
    def test_delete_emulator_success(self, mock_subprocess):
        """Test successful emulator deletion"""
        # Mock container
        mock_container = Mock()
        self.sessions['test-id'] = {
            'container': mock_container,
            'ports': {'adb': '5556'},
            'device_id': 'test123'
        }
        
        response = self.client.delete('/api/emulators/test-id')
        self.assertEqual(response.status_code, 204)
        
        # Verify container was stopped and removed
        mock_container.stop.assert_called_once()
        mock_container.remove.assert_called_once()
        
        # Verify session was removed
        self.assertNotIn('test-id', self.sessions)
    
    def test_delete_emulator_not_found(self):
        """Test deleting non-existent emulator"""
        response = self.client.delete('/api/emulators/nonexistent')
        self.assertEqual(response.status_code, 404)

if __name__ == '__main__':
    unittest.main() 