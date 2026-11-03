from unittest import TestCase
from unittest.mock import patch
from app import catalog


class CertificateSkillContractTests(TestCase):
    def test_existing_certification_response_includes_real_skill_links_without_mutation(self):
        cert={'type':'cert','usable':True,'certGroup':'data','order':1,'title':'SQL 개발자',
              'certCode':'SQLD','id':'cert_1','certShort':'SQLD','certSub':'','provider':'발급기관',
              'certVendor':None,'hours':10,'url':'https://example.com','image':'','skills':['SQL']}
        with patch.object(catalog.db,'all_',return_value=[{'group_key':'data','label':'데이터','issuer':'기관','url':''}]), \
             patch.object(catalog,'items',return_value={'cert_1':cert,'cert_2':dict(cert,id='cert_2',usable=False)}):
            result=catalog.cert_groups()
        rows=result[0]['certs']
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['skills'],['SQL'])
        rows[0]['skills'].append('edited')
        self.assertEqual(cert['skills'],['SQL'])
