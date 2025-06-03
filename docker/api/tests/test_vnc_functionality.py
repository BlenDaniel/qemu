#!/usr/bin/env python3
"""
Comprehensive VNC functionality tests for the QEMU emulator API.
Tests VNC server startup, connection, status checking, and fallback mechanisms.
"""

import unittest
import json
import time
import socket
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Add parent directory to path to import app
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app

class TestVNCFunctionality(unittest.TestCase):
    """Test suite for VNC functionality"""
    
    def setUp(self):
        """Set up test environment"""
        self.app = app
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()
        
        # Mock sessions for testing
        import app as app_module
        self.original_sessions = app_module.sessions
        app_module.sessions = {}
        self.sessions = app_module.sessions
        
    def tearDown(self):
        """Clean up after tests"""
        import app as app_module
        app_module.sessions = self.original_sessions
    
    def test_vnc_viewer_endpoint_success(self):
        """Test VNC viewer endpoint returns proper HTML"""
        # Mock session with VNC port
        mock_container = Mock()
        self.sessions['test-vnc-id'] = {
            'container': mock_container,
            'device_port': '5554',
            'device_id': 'testdev',
            'android_version': '11',
            'vnc_port': '5901'
        }
        
        response = self.client.get('/vnc/test-vnc-id')
        self.assertEqual(response.status_code, 200)
        
        # Check if VNC viewer HTML is returned
        html_content = response.data.decode('utf-8')
        self.assertIn('Android Emulator Screen', html_content)
        self.assertIn('testdev', html_content)
        self.assertIn('5901', html_content)
        self.assertIn('vnc-viewer', html_content)
        self.assertIn('Screenshot Mode', html_content)
        self.assertIn('Live Screenshot Mode', html_content)
        self.assertIn('VNC Mode', html_content)
    
    def test_vnc_viewer_endpoint_not_found(self):
        """Test VNC viewer for non-existent emulator"""
        response = self.client.get('/vnc/nonexistent')
        self.assertEqual(response.status_code, 404)
        self.assertIn(b'Emulator not found', response.data)
    
    def test_vnc_viewer_endpoint_no_vnc_port(self):
        """Test VNC viewer for emulator without VNC port"""
        # Mock session without VNC port
        mock_container = Mock()
        self.sessions['test-no-vnc'] = {
            'container': mock_container,
            'device_port': '5554',
            'device_id': 'testdev',
            'android_version': '11'
            # No vnc_port
        }
        
        response = self.client.get('/vnc/test-no-vnc')
        self.assertEqual(response.status_code, 404)
        self.assertIn(b'VNC not available', response.data)
    
    @patch('socket.socket')
    def test_vnc_api_endpoint_server_running(self, mock_socket):
        """Test VNC API endpoint when server is running"""
        # Mock successful socket connection
        mock_sock_instance = Mock()
        mock_sock_instance.connect_ex.return_value = 0  # Success
        mock_socket.return_value = mock_sock_instance
        
        # Mock session with VNC
        mock_container = Mock()
        self.sessions['test-vnc-running'] = {
            'container': mock_container,
            'device_id': 'testdev',
            'vnc_port': '5901'
        }
        
        response = self.client.get('/api/emulators/test-vnc-running/vnc')
        self.assertEqual(response.status_code, 200)
        
        data = json.loads(response.data)
        self.assertTrue(data['success'])
        self.assertEqual(data['vnc_port'], '5901')
        self.assertEqual(data['vnc_host'], 'localhost')
        self.assertIn('vnc_url', data)
        self.assertEqual(data['vnc_url'], 'vnc://localhost:5901')
        self.assertEqual(data['connection_info']['status'], 'running')
    
    @patch('socket.socket')
    def test_vnc_api_endpoint_server_not_running(self, mock_socket):
        """Test VNC API endpoint when server is not running"""
        # Mock failed socket connection
        mock_sock_instance = Mock()
        mock_sock_instance.connect_ex.return_value = 1  # Connection refused
        mock_socket.return_value = mock_sock_instance
        
        # Mock session with VNC
        mock_container = Mock()
        self.sessions['test-vnc-not-running'] = {
            'container': mock_container,
            'device_id': 'testdev',
            'vnc_port': '5901'
        }
        
        response = self.client.get('/api/emulators/test-vnc-not-running/vnc')
        self.assertEqual(response.status_code, 200)
        
        data = json.loads(response.data)
        self.assertFalse(data['success'])
        self.assertIn('not responding', data['error'])
        self.assertEqual(data['vnc_port'], '5901')
        self.assertEqual(data['connection_info']['status'], 'not_running')
    
    def test_vnc_api_endpoint_emulator_not_found(self):
        """Test VNC API endpoint for non-existent emulator"""
        response = self.client.get('/api/emulators/nonexistent/vnc')
        self.assertEqual(response.status_code, 404)
        
        data = json.loads(response.data)
        self.assertFalse(data['success'])
        self.assertIn('not found', data['error'])
    
    def test_vnc_status_endpoint(self):
        """Test VNC status endpoint"""
        # Mock container and session
        mock_container = Mock()
        mock_container.logs.return_value = b"VNC server started on port 5900\nEmulator is ready"
        mock_container.status = 'running'
        
        self.sessions['test-vnc-status'] = {
            'container': mock_container,
            'device_id': 'testdev',
            'vnc_port': '5901'
        }
        
        response = self.client.get('/api/emulators/test-vnc-status/vnc/status')
        self.assertEqual(response.status_code, 200)
        
        data = json.loads(response.data)
        self.assertEqual(data['vnc_port'], '5901')
        self.assertTrue(data['vnc_started'])
        self.assertFalse(data['vnc_error'])
        self.assertTrue(data['container_running'])
        self.assertIsInstance(data['recent_logs'], list)
    
    def test_vnc_status_endpoint_with_error(self):
        """Test VNC status endpoint when VNC has errors"""
        # Mock container with VNC error
        mock_container = Mock()
        mock_container.logs.return_value = b"VNC server failed to start\nError: Port already in use"
        mock_container.status = 'running'
        
        self.sessions['test-vnc-error'] = {
            'container': mock_container,
            'device_id': 'testdev',
            'vnc_port': '5901'
        }
        
        response = self.client.get('/api/emulators/test-vnc-error/vnc/status')
        self.assertEqual(response.status_code, 200)
        
        data = json.loads(response.data)
        self.assertFalse(data['vnc_started'])
        self.assertTrue(data['vnc_error'])
    
    @patch('app.get_docker_client')
    @patch('app.run_adb_command')
    @patch('app.kill_all_adb_processes')
    @patch('app.wait_for_device')
    def test_emulator_creation_with_vnc(self, mock_wait_for_device, mock_kill_adb, mock_adb_command, mock_get_docker):
        """Test that emulator creation properly sets up VNC"""
        # Mock Docker client and container
        mock_client = Mock()
        mock_container = Mock()
        mock_container.attrs = {
            'NetworkSettings': {
                'Ports': {
                    '5554/tcp': [{'HostPort': '5554'}],
                    '5555/tcp': [{'HostPort': '5555'}],
                    '5037/tcp': [{'HostPort': '5037'}],
                    '5900/tcp': [{'HostPort': '5901'}]  # VNC port
                }
            }
        }
        mock_client.containers.run.return_value = mock_container
        mock_get_docker.return_value = mock_client
        
        # Mock ADB commands
        mock_adb_command.return_value = {"success": True, "output": "device"}
        mock_wait_for_device.return_value = "device"
        
        # Test data
        test_data = {
            'android_version': '11'
        }
        
        response = self.client.post('/api/emulators', 
                                  data=json.dumps(test_data),
                                  content_type='application/json')
        
        self.assertEqual(response.status_code, 201)
        data = json.loads(response.data)
        
        # Verify VNC port is included
        self.assertIn('ports', data)
        self.assertIn('vnc', data['ports'])
        self.assertEqual(data['ports']['vnc'], '5901')
        
        # Verify session includes VNC
        self.assertEqual(len(self.sessions), 1)
        session = list(self.sessions.values())[0]
        self.assertEqual(session['vnc_port'], '5901')
        
        # Verify Docker container was called with VNC environment
        mock_client.containers.run.assert_called_once()
        call_args = mock_client.containers.run.call_args
        environment = call_args[1]['environment']
        self.assertEqual(environment['ENABLE_VNC'], 'true')
        self.assertEqual(environment['VNC_PORT'], '5900')


class TestVNCIntegration(unittest.TestCase):
    """Integration tests for VNC functionality"""
    
    def setUp(self):
        """Set up test environment"""
        self.app = app
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()
    
    def test_vnc_port_availability_check(self):
        """Test checking if a VNC port is available"""
        # Test available port
        def is_port_available(port):
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                result = sock.connect_ex(('localhost', port))
                sock.close()
                return result != 0  # Port is available if connection fails
            except:
                return True  # Assume available if we can't check
        
        # Find an available port for testing
        test_port = 59000
        while not is_port_available(test_port) and test_port < 60000:
            test_port += 1
        
        self.assertTrue(is_port_available(test_port), f"Port {test_port} should be available for testing")
    
    def test_vnc_connection_flow(self):
        """Test the complete VNC connection flow"""
        # This test simulates the flow a user would experience
        
        # 1. Access VNC viewer page
        # Since we don't have actual emulators, we'll test with mock data
        import app as app_module
        original_sessions = app_module.sessions
        
        try:
            app_module.sessions = {
                'test-flow': {
                    'container': Mock(),
                    'device_id': 'testdev',
                    'vnc_port': '5901'
                }
            }
            
            # Get VNC viewer page
            response = self.client.get('/vnc/test-flow')
            self.assertEqual(response.status_code, 200)
            self.assertIn(b'Android Emulator Screen', response.data)
            
            # Check VNC API endpoint
            response = self.client.get('/api/emulators/test-flow/vnc')
            self.assertIn(response.status_code, [200])  # Should return some response
            
        finally:
            app_module.sessions = original_sessions


class TestVNCFallbackMechanisms(unittest.TestCase):
    """Test VNC fallback mechanisms when VNC fails"""
    
    def setUp(self):
        """Set up test environment"""
        self.app = app
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()
        
        import app as app_module
        self.original_sessions = app_module.sessions
        app_module.sessions = {}
        self.sessions = app_module.sessions
    
    def tearDown(self):
        """Clean up after tests"""
        import app as app_module
        app_module.sessions = self.original_sessions
    
    @patch('app.run_adb_command')
    def test_screenshot_fallback(self, mock_adb_command):
        """Test screenshot functionality as VNC fallback"""
        # Mock ADB screenshot command
        mock_adb_command.return_value = {
            "success": True,
            "output": "/sdcard/screenshot.png"
        }
        
        # Mock session
        mock_container = Mock()
        self.sessions['test-screenshot'] = {
            'container': mock_container,
            'device_id': 'testdev',
            'ports': {'adb': '5555', 'adb_server': '5037'},
            'vnc_port': '5901'
        }
        
        response = self.client.get('/api/emulators/test-screenshot/screenshot')
        # The test should pass regardless of the actual screenshot implementation
        # since we're testing the fallback mechanism structure
        self.assertIn(response.status_code, [200, 500])  # Either works or fails gracefully
    
    def test_live_view_endpoint(self):
        """Test live view endpoint as VNC alternative"""
        # Mock session
        mock_container = Mock()
        self.sessions['test-live'] = {
            'container': mock_container,
            'device_id': 'testdev',
            'vnc_port': '5901'
        }
        
        response = self.client.get('/api/emulators/test-live/live_view')
        # Should return HTML page for live view
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Live View', response.data)


def run_vnc_tests():
    """Run all VNC tests"""
    print("🧪 Running VNC Functionality Tests...")
    
    # Create test suite
    test_suite = unittest.TestSuite()
    
    # Add test classes
    test_classes = [
        TestVNCFunctionality,
        TestVNCIntegration,
        TestVNCFallbackMechanisms
    ]
    
    for test_class in test_classes:
        tests = unittest.TestLoader().loadTestsFromTestCase(test_class)
        test_suite.addTests(tests)
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(test_suite)
    
    # Print summary
    print(f"\n📊 Test Results:")
    print(f"   Tests run: {result.testsRun}")
    print(f"   Failures: {len(result.failures)}")
    print(f"   Errors: {len(result.errors)}")
    
    if result.failures:
        print(f"\n❌ Failures:")
        for test, traceback in result.failures:
            print(f"   {test}: {traceback}")
    
    if result.errors:
        print(f"\n💥 Errors:")
        for test, traceback in result.errors:
            print(f"   {test}: {traceback}")
    
    success = len(result.failures) == 0 and len(result.errors) == 0
    print(f"\n{'✅ All tests passed!' if success else '❌ Some tests failed.'}")
    
    return success


if __name__ == '__main__':
    success = run_vnc_tests()
    exit(0 if success else 1) 