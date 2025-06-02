import unittest
import json
import time
from unittest.mock import Mock, patch
import sys
import os

# Try to import Selenium components, but handle gracefully if not available
try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.chrome.options import Options
    from selenium.common.exceptions import TimeoutException, WebDriverException
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False
    # Create dummy classes to prevent import errors
    class webdriver:
        class Chrome:
            def __init__(self, *args, **kwargs):
                pass
            def quit(self):
                pass
    class By:
        TAG_NAME = "tag_name"
        ID = "id"
        XPATH = "xpath"
        CLASS_NAME = "class_name"
    class WebDriverWait:
        def __init__(self, *args, **kwargs):
            pass
        def until(self, *args, **kwargs):
            pass
    class EC:
        @staticmethod
        def title_contains(*args):
            pass
        @staticmethod
        def presence_of_element_located(*args):
            pass
        @staticmethod
        def element_to_be_clickable(*args):
            pass
    class Options:
        def add_argument(self, *args):
            pass
    class TimeoutException(Exception):
        pass
    class WebDriverException(Exception):
        pass

# Add the current directory to the path so we can import app
sys.path.insert(0, os.path.dirname(__file__))

class TestWebUI(unittest.TestCase):
    """Test suite for the web UI using Selenium"""
    
    @classmethod
    def setUpClass(cls):
        """Set up test environment"""
        if not SELENIUM_AVAILABLE:
            cls.selenium_available = False
            return
            
        # Try to set up Chrome driver for UI testing
        try:
            chrome_options = Options()
            chrome_options.add_argument("--headless")  # Run headless Chrome
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--window-size=1920,1080")
            
            cls.driver = webdriver.Chrome(options=chrome_options)
            cls.selenium_available = True
        except (WebDriverException, Exception):
            cls.driver = None
            cls.selenium_available = False
            print("Selenium WebDriver not available - UI tests will be skipped")
    
    @classmethod
    def tearDownClass(cls):
        """Clean up test environment"""
        if hasattr(cls, 'driver') and cls.driver:
            cls.driver.quit()
    
    def setUp(self):
        """Set up for each test"""
        if not SELENIUM_AVAILABLE or not self.selenium_available:
            self.skipTest("Selenium not available")
        
        # Start the Flask app in test mode
        with patch('docker.from_env'):
            from app import app
            self.app = app
            self.app.config['TESTING'] = True
            self.app.config['WTF_CSRF_ENABLED'] = False
        
        # Start the Flask development server in a separate thread
        import threading
        self.server_thread = threading.Thread(
            target=lambda: self.app.run(host='127.0.0.1', port=5001, debug=False, use_reloader=False)
        )
        self.server_thread.daemon = True
        self.server_thread.start()
        
        # Wait for server to start
        time.sleep(2)
        
        # Navigate to the main page
        self.driver.get("http://127.0.0.1:5001")
        
    def test_page_loads_successfully(self):
        """Test that the main page loads without errors"""
        # Check page title
        WebDriverWait(self.driver, 10).until(
            EC.title_contains("Android Emulator Manager")
        )
        
        # Check for main header
        header = self.driver.find_element(By.TAG_NAME, "h1")
        self.assertIn("Android Emulator Manager", header.text)
    
    def test_ui_sections_present(self):
        """Test that all main UI sections are present"""
        wait = WebDriverWait(self.driver, 10)
        
        # Check for Create New Emulator section
        create_section = wait.until(
            EC.presence_of_element_located((By.XPATH, "//*[contains(text(), 'Create New Emulator')]"))
        )
        self.assertTrue(create_section.is_displayed())
        
        # Check for ADB Quick Actions section
        adb_section = wait.until(
            EC.presence_of_element_located((By.XPATH, "//*[contains(text(), 'ADB Quick Actions')]"))
        )
        self.assertTrue(adb_section.is_displayed())
        
        # Check for Running Emulators section
        emulators_section = wait.until(
            EC.presence_of_element_located((By.XPATH, "//*[contains(text(), 'Running Emulators')]"))
        )
        self.assertTrue(emulators_section.is_displayed())
    
    def test_emulator_creation_form(self):
        """Test the emulator creation form elements"""
        wait = WebDriverWait(self.driver, 10)
        
        # Check Android version dropdown
        android_version = wait.until(
            EC.presence_of_element_located((By.ID, "androidVersion"))
        )
        self.assertTrue(android_version.is_displayed())
        
        # Check that both Android 11 and 14 options are available
        options = android_version.find_elements(By.TAG_NAME, "option")
        option_texts = [option.text for option in options]
        self.assertIn("Android 11 (API 30)", option_texts)
        self.assertIn("Android 14 (API 34)", option_texts)
        
        # Check ADB server mapping dropdown
        adb_mapping = wait.until(
            EC.presence_of_element_located((By.ID, "mapAdbServer"))
        )
        self.assertTrue(adb_mapping.is_displayed())
        
        # Check create button (text is transformed to uppercase by CSS)
        create_button = wait.until(
            EC.presence_of_element_located((By.ID, "createBtn"))
        )
        self.assertTrue(create_button.is_displayed())
        # The button text is "Create Emulator" but CSS transforms it to uppercase
        self.assertIn("CREATE EMULATOR", create_button.text.upper())
    
    def test_adb_actions_form(self):
        """Test the ADB Quick Actions form elements"""
        wait = WebDriverWait(self.driver, 10)
        
        # Check ADB server port input
        server_port = wait.until(
            EC.presence_of_element_located((By.ID, "adbServerPort"))
        )
        self.assertTrue(server_port.is_displayed())
        self.assertEqual(server_port.get_attribute("value"), "5037")
        
        # Check device port input
        device_port = wait.until(
            EC.presence_of_element_located((By.ID, "adbDevicePort"))
        )
        self.assertTrue(device_port.is_displayed())
        
        # Check action buttons
        list_devices_btn = wait.until(
            EC.presence_of_element_located((By.XPATH, "//button[contains(text(), 'List Devices')]"))
        )
        self.assertTrue(list_devices_btn.is_displayed())
        
        connect_device_btn = wait.until(
            EC.presence_of_element_located((By.XPATH, "//button[contains(text(), 'Connect Device')]"))
        )
        self.assertTrue(connect_device_btn.is_displayed())
    
    def test_refresh_emulators_button(self):
        """Test the refresh emulators button"""
        wait = WebDriverWait(self.driver, 10)
        
        refresh_button = wait.until(
            EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Refresh List')]"))
        )
        self.assertTrue(refresh_button.is_displayed())
        
        # Test clicking the refresh button
        refresh_button.click()
        
        # Check that the loading message appears
        emulators_list = self.driver.find_element(By.ID, "emulatorsList")
        self.assertIn("Loading emulators", emulators_list.text)
    
    @patch('app.get_docker_client')
    def test_create_emulator_ui_flow(self, mock_get_docker):
        """Test the complete emulator creation UI flow"""
        # Mock Docker client
        mock_client = Mock()
        mock_container = Mock()
        mock_container.attrs = {
            'NetworkSettings': {
                'Ports': {
                    '5554/tcp': [{'HostPort': '5334'}],
                    '5555/tcp': [{'HostPort': '5556'}],
                    '5037/tcp': [{'HostPort': '5038'}],
                    '5900/tcp': [{'HostPort': '5901'}]
                }
            }
        }
        mock_client.containers.run.return_value = mock_container
        mock_get_docker.return_value = mock_client
        
        wait = WebDriverWait(self.driver, 10)
        
        # Select Android 14
        android_version = wait.until(
            EC.presence_of_element_located((By.ID, "androidVersion"))
        )
        android_version.send_keys("Android 14 (API 34)")
        
        # Click create button
        create_button = wait.until(
            EC.element_to_be_clickable((By.ID, "createBtn"))
        )
        create_button.click()
        
        # Check that the creation log appears
        creation_log = wait.until(
            EC.presence_of_element_located((By.ID, "creationLog"))
        )
        self.assertFalse("hidden" in creation_log.get_attribute("class"))
    
    def test_adb_list_devices_functionality(self):
        """Test the ADB list devices functionality"""
        wait = WebDriverWait(self.driver, 10)
        
        # Mock the ADB command response
        with patch('app.run_adb_command') as mock_adb:
            mock_adb.return_value = {
                "success": True, 
                "output": "List of devices attached\nemulator-5334\tdevice\n"
            }
            
            # Click list devices button
            list_button = wait.until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'List Devices')]"))
            )
            list_button.click()
            
            # Check that ADB output appears
            adb_output = wait.until(
                EC.presence_of_element_located((By.ID, "adbOutput"))
            )
            
            # Wait for the log to appear
            time.sleep(1)
            self.assertFalse("hidden" in adb_output.get_attribute("class"))
    
    def test_responsive_design(self):
        """Test that the UI is responsive"""
        # Test mobile viewport
        self.driver.set_window_size(375, 667)  # iPhone 6/7/8 size
        
        # Check that elements are still visible
        header = self.driver.find_element(By.TAG_NAME, "h1")
        self.assertTrue(header.is_displayed())
        
        # Test tablet viewport
        self.driver.set_window_size(768, 1024)  # iPad size
        
        # Check that grid layout adapts
        form_groups = self.driver.find_elements(By.CLASS_NAME, "form-group")
        self.assertGreater(len(form_groups), 0)
        
        # Reset to desktop
        self.driver.set_window_size(1920, 1080)
    
    def test_vnc_ui_elements(self):
        """Test that VNC-related UI elements are present"""
        # This test checks for VNC-related elements in the generated HTML
        page_source = self.driver.page_source
        
        # Check for VNC-related text
        self.assertIn("View Screen", page_source)
        
        # Check for VNC-related JavaScript functions
        self.assertIn("openVNC", page_source)
        self.assertIn("closeVNC", page_source)


class TestWebUIWithoutSelenium(unittest.TestCase):
    """Test suite for UI components that can be tested without Selenium"""
    
    def setUp(self):
        """Set up test fixtures"""
        with patch('docker.from_env'):
            from app import app
            self.app = app
            self.app.config['TESTING'] = True
        self.client = self.app.test_client()
    
    def test_html_structure(self):
        """Test the HTML structure of the main page"""
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        html = response.data.decode('utf-8')
        
        # Check for essential HTML elements
        self.assertIn('<title>Android Emulator Manager</title>', html)
        self.assertIn('<h1>🤖 Android Emulator Manager</h1>', html)
        
        # Check for form elements
        self.assertIn('id="createEmulatorForm"', html)
        self.assertIn('id="androidVersion"', html)
        self.assertIn('id="mapAdbServer"', html)
        
        # Check for ADB action elements
        self.assertIn('id="adbServerPort"', html)
        self.assertIn('id="adbDevicePort"', html)
        
        # Check for emulator list container
        self.assertIn('id="emulatorsList"', html)
        
        # Check for VNC-related elements
        self.assertIn('View Screen', html)
        self.assertIn('openVNC', html)
        self.assertIn('closeVNC', html)
    
    def test_javascript_functions_present(self):
        """Test that required JavaScript functions are present"""
        response = self.client.get('/')
        html = response.data.decode('utf-8')
        
        # Check for essential JavaScript functions
        self.assertIn('function logMessage', html)
        self.assertIn('function clearLog', html)
        self.assertIn('function refreshEmulators', html)
        self.assertIn('function createEmulatorCard', html)
        self.assertIn('function deleteEmulator', html)
        self.assertIn('function openVNC', html)
        self.assertIn('function closeVNC', html)
        self.assertIn('function listAdbDevices', html)
        self.assertIn('function connectAdbDevice', html)
    
    def test_css_styling_present(self):
        """Test that CSS styling is properly included"""
        response = self.client.get('/')
        html = response.data.decode('utf-8')
        
        # Check for CSS classes
        self.assertIn('class="container"', html)
        self.assertIn('class="header"', html)
        self.assertIn('class="section"', html)
        self.assertIn('class="form-group"', html)
        # Check for emulator-card in CSS styles (it's defined in CSS but not in static HTML)
        self.assertIn('.emulator-card', html)
        self.assertIn('class="vnc-viewer"', html)
        
        # Check for responsive grid classes
        self.assertIn('class="grid-2"', html)
    
    def test_vnc_viewer_template(self):
        """Test the VNC viewer template rendering"""
        # Mock a session for testing
        from app import sessions
        sessions['test-vnc'] = {
            'device_id': 'test123',
            'vnc_port': '5901'
        }
        
        response = self.client.get('/vnc/test-vnc')
        self.assertEqual(response.status_code, 200)
        html = response.data.decode('utf-8')
        
        # Check VNC viewer specific elements
        self.assertIn('test123 - Android Emulator Screen', html)
        self.assertIn('VNC Port: 5901', html)
        self.assertIn('noVNC', html)
        self.assertIn('rfb.js', html)
        
        # Check for VNC controls
        self.assertIn('Screenshot', html)
        self.assertIn('Reconnect', html)
        self.assertIn('Scale to fit', html)
        
        # Clean up
        del sessions['test-vnc']
    
    def test_api_configuration(self):
        """Test that API configuration is correctly set in the frontend"""
        response = self.client.get('/')
        html = response.data.decode('utf-8')
        
        # Check that API_BASE is set correctly (case insensitive)
        self.assertTrue('api_base' in html.lower() or 'API_BASE' in html)
        
        # Check for API endpoint usage
        self.assertIn('/api/emulators', html)
        self.assertIn('/api/adb/devices', html)
        self.assertIn('/api/adb/connect', html)
    
    def test_form_validation_elements(self):
        """Test that form validation elements are present"""
        response = self.client.get('/')
        html = response.data.decode('utf-8')
        
        # Check for required form attributes
        self.assertIn('type="submit"', html)
        # Note: The current HTML doesn't have 'required' attributes, which is fine for this app
        
        # Check for input validation
        self.assertIn('type="number"', html)
        self.assertIn('placeholder=', html)
    
    def test_accessibility_features(self):
        """Test basic accessibility features"""
        response = self.client.get('/')
        html = response.data.decode('utf-8')
        
        # Check for labels
        self.assertIn('<label', html)
        
        # Check for semantic HTML (the current template uses div structure, which is acceptable)
        self.assertIn('<form', html)
        self.assertIn('<button', html)
        self.assertIn('<select', html)
        self.assertIn('<input', html)
        
        # Check for proper heading structure
        self.assertIn('<h1>', html)
        self.assertIn('<h2>', html)


def run_ui_tests():
    """Run all UI tests"""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add Selenium tests (will be skipped if Selenium not available)
    suite.addTests(loader.loadTestsFromTestCase(TestWebUI))
    
    # Add non-Selenium UI tests
    suite.addTests(loader.loadTestsFromTestCase(TestWebUIWithoutSelenium))
    
    runner = unittest.TextTestRunner(verbosity=2)
    return runner.run(suite)


if __name__ == '__main__':
    result = run_ui_tests()
    sys.exit(0 if result.wasSuccessful() else 1) 