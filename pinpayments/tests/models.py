import json
from django.conf import settings
from django.test import TestCase
from django.test.utils import override_settings
from mock import patch
from pinpayments.models import (
    ConfigError,
    CustomerToken,
    PinError,
    PinTransaction
)
from requests import Response

ENV_MISSING_SECRET = {
    'test': {
        'key': 'key1',
        'host': 'test-api.pin.net.au',
    },
}

ENV_MISSING_HOST = {
    'test': {
        'key': 'key1',
        'secret': 'secret1',
    },
}

class FakeResponse(Response):
    def __init__(self, status_code, content):
        super(FakeResponse, self).__init__()
        self.status_code = status_code
        self._content = content

class ModelTests(TestCase):
    def setUp(self):
        super(ModelTests, self).setUp()
        self.transaction = PinTransaction()
        self.transaction.card_token = '12345'
        self.transaction.ip_address = '127.0.0.1'
        self.transaction.amount = 500
        self.transaction.currency = 'AUD'
        self.transaction.email_address = 'test@example.com'
        self.transaction.environment = 'test'

    # Need to override the setting so we can delete it, not sure why.
    @override_settings(PIN_DEFAULT_ENVIRONMENT=None)
    def test_save_defaults(self):
        # Unset PIN_DEFAULT_ENVIRONMENT to test that the environment defaults
        # to 'test'.
        del settings.PIN_DEFAULT_ENVIRONMENT
        self.transaction.environment = None
        self.transaction.save()
        self.assertEqual(self.transaction.environment, 'test')
        self.assertTrue(self.transaction.date)

    def test_save_card_or_customer_token(self):
        self.transaction.card_token = None
        self.transaction.customer_token = None
        self.assertRaises(self.transaction.save, PinError)

    def test_valid_environment(self):
        self.transaction.environment = 'this should not exist'
        self.assertRaises(self.transaction.save, PinError)

class ProcessTransactionsTests(TestCase):
    def setUp(self):
        super(ProcessTransactionsTests, self).setUp()
        self.transaction = PinTransaction()
        self.transaction.card_token = '12345'
        self.transaction.ip_address = '127.0.0.1'
        self.transaction.amount = 500
        self.transaction.currency = 'AUD'
        self.transaction.email_address = 'test@example.com'
        self.transaction.environment = 'test'
        self.transaction.save()
        self.response_data = json.dumps({
            'response': {
                'token': '12345',
                'success': True,
                'amount': 500,
                'total_fees': 500,
                'currency': 'AUD',
                'description': 'test charge',
                'email': 'test@example.com',
                'ip_address': '127.0.0.1',
                'created_at': '2012-06-20T03:10:49Z',
                'status_message': 'Success!',
                'error_message': None,
                'card': {
                    'token': 'card_nytGw7koRg23EEp9NTmz9w',
                    'display_number': 'XXXX-XXXX-XXXX-0000',
                    'scheme': 'master',
                    'address_line1': '42 Sevenoaks St',
                    'address_line2': None,
                    'address_city': 'Lathlain',
                    'address_postcode': '6454',
                    'address_state': 'WA',
                    'address_country': 'Australia'
                },
                'transfer': None
            }
        })

    @patch('requests.post')
    def test_only_process_once(self, mock_request):
        mock_request.return_value = FakeResponse(200, self.response_data)

        # Shouldn't be marked as processed before process_transaction is called
        # for the first time.
        self.assertFalse(self.transaction.processed)

        # Should be marked after the first call.
        result = self.transaction.process_transaction()
        self.assertTrue(self.transaction.processed)

        # Shouldn't process anything the second time
        result = self.transaction.process_transaction()
        self.assertIsNone(result)

    @override_settings(PIN_ENVIRONMENTS={})
    @patch('requests.post')
    def test_valid_environment(self, mock_request):
        mock_request.return_value = FakeResponse(200, self.response_data)
        self.assertRaises(self.transaction.process_transaction, PinError)

    @override_settings(PIN_ENVIRONMENTS=ENV_MISSING_SECRET)
    @patch('requests.post')
    def test_secret_set(self, mock_request):
        mock_request.return_value = FakeResponse(200, self.response_data)
        self.assertRaises(self.transaction.process_transaction, ConfigError)

    @override_settings(PIN_ENVIRONMENTS=ENV_MISSING_HOST)
    @patch('requests.post')
    def test_host_set(self, mock_request):
        mock_request.return_value = FakeResponse(200, self.response_data)
        self.assertRaises(self.transaction.process_transaction, ConfigError)

    @patch('requests.post')
    def test_response_not_json(self, mock_request):
        mock_request.return_value = FakeResponse(200, '')
        response = self.transaction.process_transaction()
        self.assertEqual(response, 'Failure.')

