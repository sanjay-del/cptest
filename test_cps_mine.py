from inspect import signature
import json
import os
from typing import Union, List
from iconsdk.exception import JSONRPCException
from iconsdk.builder.call_builder import CallBuilder
from iconsdk.builder.transaction_builder import TransactionBuilder, DeployTransactionBuilder, CallTransactionBuilder
from iconsdk.exception import AddressException
from iconsdk.libs.in_memory_zip import gen_deploy_data_content
from iconsdk.signed_transaction import SignedTransaction
from iconsdk.wallet.wallet import KeyWallet, Wallet
from iconservice import icon_service_engine
from iconservice.base.address import Address
from tbears.config.tbears_config import TEST1_PRIVATE_KEY, tbears_server_config, TConfigKey as TbConf
from tbears.libs.icon_integrate_test import Account
from tbears.libs.icon_integrate_test import IconIntegrateTestBase, SCORE_INSTALL_ADDRESS
from iconsdk.icon_service import IconService
from iconsdk.providers.http_provider import HTTPProvider

SCORES = os.path.abspath('')
DEPLOY = ['cps_score', 'CPFTreasury', 'CPSTreasury']
SCORE_ADDRESS = "scoreAddress"


def get_key(my_dict: dict, value: Union[str, int]):
    return list(my_dict.keys())[list(my_dict.values()).index(value)]


class BaseTestUtils(IconIntegrateTestBase):

    def setUp(self,
              genesis_accounts: List[Account] = None,
              block_confirm_interval: int = tbears_server_config[TbConf.BLOCK_CONFIRM_INTERVAL],
              network_only: bool = False,
              network_delay_ms: int = tbears_server_config[TbConf.NETWORK_DELAY_MS],
              icon_service: IconService = None,
              nid: int = 3,
              tx_result_wait: int = 3):
        super().setUp(genesis_accounts, block_confirm_interval, network_only, network_delay_ms)
        self.icon_service = icon_service
        self.nid = nid
        self.tx_result_wait = tx_result_wait

    def deploy_tx(self,
                  from_: KeyWallet,
                  to: str = SCORE_INSTALL_ADDRESS,
                  value: int = 0,
                  content: str = None,
                  params: dict = None) -> dict:

        signed_transaction = self.build_deploy_tx(from_, to, value, content, params)
        tx_result = self.process_transaction(signed_transaction, network=self.icon_service,
                                             block_confirm_interval=self.tx_result_wait)

        self.assertTrue('status' in tx_result, tx_result)
        self.assertEqual(1, tx_result['status'], f"Failure: {tx_result['failure']}" if tx_result['status'] == 0 else "")
        self.assertTrue('scoreAddress' in tx_result)

        return tx_result

    def build_deploy_tx(self,
                        from_: KeyWallet,
                        to: str = SCORE_INSTALL_ADDRESS,
                        value: int = 0,
                        content: str = None,
                        params: dict = None,
                        step_limit: int = 3_000_000_000,
                        nonce: int = 100) -> SignedTransaction:
        print(f"---------------------------Deploying contract: {content}---------------------------------------")
        params = {} if params is None else params
        transaction = DeployTransactionBuilder() \
            .from_(from_.get_address()) \
            .to(to) \
            .value(value) \
            .step_limit(step_limit) \
            .nid(self.nid) \
            .nonce(nonce) \
            .content_type("application/zip") \
            .content(gen_deploy_data_content(content)) \
            .params(params) \
            .build()

        signed_transaction = SignedTransaction(transaction, from_)
        return signed_transaction

    def send_icx(self, from_: KeyWallet, to: str, value: int):
        previous_to_balance = self.get_balance(to)
        previous_from_balance = self.get_balance(from_.get_address())

        signed_icx_transaction = self.build_send_icx(from_, to, value)
        tx_result = self.process_transaction(signed_icx_transaction, self.icon_service, self.tx_result_wait)

        self.assertTrue('status' in tx_result, tx_result)
        self.assertEqual(1, tx_result['status'], f"Failure: {tx_result['failure']}" if tx_result['status'] == 0 else "")
        fee = tx_result['stepPrice'] * tx_result['cumulativeStepUsed']
        self.assertEqual(previous_to_balance + value, self.get_balance(to))
        self.assertEqual(previous_from_balance - value - fee, self.get_balance(from_.get_address()))

    def build_send_icx(self, from_: KeyWallet, to: str, value: int,
                       step_limit: int = 1000000, nonce: int = 3) -> SignedTransaction:
        send_icx_transaction = TransactionBuilder(
            from_=from_.get_address(),
            to=to,
            value=value,
            step_limit=step_limit,
            nid=self.nid,
            nonce=nonce
        ).build()
        signed_icx_transaction = SignedTransaction(send_icx_transaction, from_)
        return signed_icx_transaction

    def get_balance(self, address: str) -> int:
        if self.icon_service is not None:
            return self.icon_service.get_balance(address)
        params = {'address': Address.from_string(address)}
        response = self.icon_service_engine.query(method="icx_getBalance", params=params)
        return response

    def send_tx(self, from_: KeyWallet, to: str, value: int = 0, method: str = None, params: dict = None) -> dict:
        print(f"------------Calling {method}, with params={params} to {to} contract----------")
        signed_transaction = self.build_tx(from_, to, value, method, params)
        tx_result = self.process_transaction(signed_transaction, self.icon_service, self.tx_result_wait)

        self.assertTrue('status' in tx_result)
        self.assertEqual(1, tx_result['status'], f"Failure: {tx_result['failure']}" if tx_result['status'] == 0 else "")
        return tx_result

    def build_tx(self, from_: KeyWallet, to: str, value: int = 0, method: str = None, params: dict = None) \
            -> SignedTransaction:
        params = {} if params is None else params
        tx = CallTransactionBuilder(
            from_=from_.get_address(),
            to=to,
            value=value,
            step_limit=3_000_000_000,
            nid=self.nid,
            nonce=5,
            method=method,
            params=params
        ).build()
        signed_transaction = SignedTransaction(tx, from_)
        return signed_transaction

    def call_tx(self, to: str, method: str, params: dict = None):

        params = {} if params is None else params
        call = CallBuilder(
            to=to,
            method=method,
            params=params
        ).build()
        response = self.process_call(call, self.icon_service)
        print(f"-----Reading method={method}, with params={params} on the {to} contract------")
        print(f"-------------------The output is: : {response}")
        return response
    
    # def call_tx(self, _score, params, method):
    #     params = {} if params is None else params
    #     _call = CallBuilder() \
    #         .from_(self._test1.get_address()) \
    #         .to(_score) \
    #         .method(method) \
    #         .params(params) \
    #         .build()
    #     response = self.process_call(_call, self.icon_service)
    #     return response

    
class TestCPS(BaseTestUtils):
    # CPS_SCORE_PROJECT = os.path.abspath((os.path.join(DIR_PATH, '..', 'cps_score')))
    # CPF_TREASURY_PROJECT = os.path.abspath((os.path.join(DIR_PATH, '..', 'CPFTreasury')))
    # CPS_TREASURY_PROJECT = os.path.abspath((os.path.join(DIR_PATH, '..', 'CPSTreasury')))
    BLOCK_INTERVAL = 6
    
    def setUp(self):
        
        self._wallet_setup()
        super().setUp(genesis_accounts=self.genesis_accounts,
                  block_confirm_interval=2,
                  network_delay_ms=0,
                  network_only=False,
                  icon_service=None, #icon_service=IconService(HTTPProvider("http://127.0.0.1:9000", 3)),
                  nid=3,
                  tx_result_wait=4
                  )
        self.contracts = {}
        # self.PREPS = {
        # self._wallet_array[1].get_address(),
        # self._wallet_array[2].get_address(),
        # self._wallet_array[3].get_address(),
        # self._wallet_array[4].get_address(),
        # self._wallet_array[5].get_address(),
        # self._wallet_array[6].get_address(),
        # self._wallet_array[7].get_address()
        # }
      
        self._deploy_all()
    
    def _wallet_setup(self):
        self.icx_factor = 10 ** 18
        self.user1: 'KeyWallet' = self._wallet_array[5]
        self.user2: 'KeyWallet' = self._wallet_array[6]
        self.genesis_accounts = [
        Account("user1", Address.from_string(self.user1.get_address()), 100_000_000 * self.icx_factor),
        Account("user2", Address.from_string(self.user2.get_address()), 100_000_000 * self.icx_factor),
    ]
        
    def _deploy_all(self):
        txs =[]
        params = {}
        for address in DEPLOY:
            # if address == 'CPFTreasury':
            #     params = {'amount': 1_000_000 * 10 ** 18}
            
            self.SCORE_PROJECT = SCORES + "/" + address
            print(self.SCORE_PROJECT)
            print(f'Deploying {address}')
            self.contracts[address] = self.deploy_tx(from_ = self._test1,
                                                to = SCORE_INSTALL_ADDRESS,
                                                value = 0,
                                                 content=self.SCORE_PROJECT,
                                                 params=params)['scoreAddress']
    
    def test_update(self):
        for address in DEPLOY:
            self.SCOREPROJECT = SCORES + '/' + address
            tx_result= self.deploy_tx(
                from_ = self._test1,
                to = self.contracts[address],
                content=self.SCOREPROJECT
            )
            print(f"Adress of {address} is {tx_result['scoreAddress']}")
            self.assertEqual(self.contracts[address], tx_result['scoreAddress'])
    
    def _add_admin(self):
        self.build_tx(self._test1, self.contracts['cps_score'], 0, 'add_admin', {'_address': self._test1.get_address()})

    def _set_cps_treasury_score(self):
        self._add_admin()
        self.build_tx(self._test1, self.contracts['cps_score'], 0, 'set_cps_treasury_score',
                               {'_score': self.contracts['CPSTreasury']})

    def _set_cpf_treasury_score(self):
        self._add_admin()
        self.build_tx(self._test1, self.contracts['cps_score'], 0, 'set_cpf_treasury_score', {'_score':self.contracts['CPFTreasury']})
        
    def test_submit_proposal(self):
        self._add_fund()
        proposal_parameters = {'ipfs_hash': 'bafybeie5cifgwgu2x3guixgrs67miydug7ocyp6yia5kxv3imve6fthbs4',
                               'project_title': 'Test Proposal',
                               'project_duration': 3,
                               'total_budget': 3182,
                               'sponsor_address': self._wallet_array[10].get_address(),
                               'ipfs_link': 'test.link@link.com'}
        self._set_cps_treasury_score()
        self._set_cpf_treasury_score()
        print(self.call_tx(self.contracts['cps_score'], None, "get_period_status"))
        self._set_initial_block()
        self._register_prep()
        print(self.call_tx(self.contracts['cps_score'], None, "get_period_status"))  # application period
        tx_result = self.send_tx(self._test1, self.contracts['cps_score'], 50 * 10 ** 18, "submit_proposal",
                                 {'_proposals': proposal_parameters})
        print(tx_result)
        print(self.call_tx(self.contracts['cps_score'], None, "get_period_status"))
        self.assertEqual(tx_result['eventLogs'][0]['data'][0], 'Successfully submitted a Proposal.')

    def _add_fund(self):
            self.send_tx(self._test1, self.contracts['CPFTreasury'], 5000 * 10 ** 18, "add_fund", None)

    def _set_initial_block(self):
        self.send_tx(self._test1, self.contracts['cps_score'], 0, "set_initialBlock", None)
    
    def _register_prep(self):
        print(f'Wallet address: {self._wallet_array[10].get_address()}')

        print(self.send_tx(self._wallet_array[10], self.contracts['cps_score'], 0, 'register_prep', None))
        print(self.send_tx(self._wallet_array[11], self.contracts['cps_score'], 0, 'register_prep', None))
        print(self.send_tx(self._wallet_array[12], self.contracts['cps_score'], 0, 'register_prep', None))
        print(self.send_tx(self._wallet_array[13], self.contracts['cps_score'], 0, 'register_prep', None))
        print(self.send_tx(self._wallet_array[14], self.contracts['cps_score'], 0, 'register_prep', None))
        print(self.send_tx(self._wallet_array[15], self.contracts['cps_score'], 0, 'register_prep', None))
        print(self.send_tx(self._wallet_array[16], self.contracts['cps_score'], 0, 'register_prep', None))
        
    def _submit_proposal(self):
        self._add_fund()
        proposal_parameters = {'ipfs_hash': 'bafybeie5cifgwgu2x3guixgrs67miydug7ocyp6yia5kxv3imve6fthbs4',
                               'project_title': 'Test Proposal',
                               'project_duration': 3,
                               'total_budget': 3182,
                               'sponsor_address': self._wallet_array[10].get_address(),
                               'ipfs_link': 'test.link@link.com'}
        self._set_cps_treasury_score()
        self._set_cpf_treasury_score()
        self._set_initial_block()
        self._register_prep()
        tx_result = self.send_tx(self._test1, self.contracts['cps_score'], 50 * 10 ** 18, "submit_proposal",
                                 {'_proposals': proposal_parameters})
        print(tx_result)
