#coding=utf-8
#based on https://github.com/Leryan/python-simplecacher

import shutil
import os

from os.path import abspath
from os.path import join as pathjoin

import ssl_config as conf
from utils import popen_process, popen_fulloutput

#helpers

def get_openssl():
    for path in conf.default_openssl_bins:
        p=popen_process('%s version'%path)
        if not p[3] and not p[2]: # errcode==0 and stderr==b''
            print('ssl: OpenSSL executable found at %s: %s'%(path,popen_fulloutput(p).rstrip()))
            return path
    print('ssl: critical: cannot find a OpenSSL executable. edit `const.py` for a custom one.')
    raise RuntimeError('no openssl bin')
OBIN=get_openssl()

if not os.path.exists('ssl_stuff/serial'):
    print('ssl: initializing serial')
    with open('ssl_stuff/serial','w') as f:
        f.write('00\n')
        
with open(conf.ca_openssl_config) as f:
    TEMPLATE=f.read()

#from tlsmanager.py

class CertManager(object):
    OPENSSL_NEWKEY_FORMAT = '{OBIN} req  -new -config {CONFIG} -keyform PEM -keyout {KEYOUT} -outform PEM -out {OUT} -nodes -newkey 1024'
    OPENSSL_CASIGN_FORMAT = '{OBIN} x509 -CA {0} -CAkey {1} -CAserial {2} -req -sha256 -in {3} -outform PEM -out {4} -days {5} -extensions v3_req -extfile {CONFIG}'

    def __init__(self, *args, **kwargs):
        self.key_dir = self.normpath(conf.key_dir)
        self.ca_key = self.normpath(conf.ca_key_file)
        self.ca_crt = self.normpath(conf.ca_crt_file)
        self.ca_ser = self.normpath(conf.ca_serial_file)
        self.obin = OBIN
        self.validity_days = int(conf.validity_days)

        self.prepare()
        super(CertManager, self).__init__()

    @staticmethod
    def normpath(path):
        path = os.path.normpath(path)
        path = path.replace('~', os.path.expanduser('~'))
        path = abspath(path)
        return path

    def prepare(self):
        if not os.path.isdir(self.key_dir):
            os.makedirs(self.key_dir)

    @staticmethod
    def sanitize_domain(domain):
        if len(domain) > 64:
            sdomain = domain.split('.')
            domain = '*.' + '.'.join(sdomain[1:])
        return domain, domain.replace('*', 'wildcard')

    def generate(self, domain, force=False):
        domain, fdomain = self.sanitize_domain(domain)

        if self.check_cert(domain) and not force:
            #SCLogger.tls.debug('Certificate for {0} is ok'.format(domain))
            return True, fdomain

        ssl_key = pathjoin(self.key_dir, fdomain + '.key')
        ssl_cert = pathjoin(self.key_dir, fdomain + '.crt')
        ssl_csr = pathjoin(self.key_dir, fdomain + '.csr')

        if not self.check_cert(domain):
            self.cleanup(domain)

        print('ssl: generating new cert for {0}'.format(domain))
        CONFIG_FILE='_generated_keys/%s.cnf'%fdomain
        with open(CONFIG_FILE,'w') as f:
            f.write(TEMPLATE.replace('{{domain}}',domain))
        cmd_key = self.OPENSSL_NEWKEY_FORMAT.format(
            CONFIG=CONFIG_FILE,
            KEYOUT=ssl_key,
            OUT=ssl_csr,
            OBIN=self.obin,
        )
        ssl_log_key = popen_process(cmd_key)
        cmd_cert = self.OPENSSL_CASIGN_FORMAT.format(
            self.ca_crt,
            self.ca_key,
            self.ca_ser,
            ssl_csr,
            ssl_cert,
            self.validity_days,
            OBIN=self.obin,
            CONFIG=CONFIG_FILE,
        )
        ssl_log_cert = popen_process(cmd_cert)

        cert_check = self.check_cert(domain)
        if not cert_check:
            ssl_log_key_full = popen_fulloutput(ssl_log_key)
            ssl_log_cert_full = popen_fulloutput(ssl_log_cert)
            print('ssl: error: cert for {0} has NOT been generated'.format(domain))
            print('  OpenSSL output for {0}.key:\n{1}'.format(domain, ssl_log_key_full))
            print('  OpenSSL output for {0}.crt:\n{1}'.format(domain, ssl_log_cert_full))

        return cert_check, fdomain

    def check_cert(self, domain):
        # fixme: check certificate real validity
        domain, fdomain = self.sanitize_domain(domain)
        return all(
            map(os.path.isfile,
                (
                    pathjoin(self.key_dir, fdomain + '.key'),
                    pathjoin(self.key_dir, fdomain + '.crt'),)))

    def cleanup(self, domain=None):
        try:
            if not domain:
                shutil.rmtree(self.key_dir)
            else:
                domain, fdomain = self.sanitize_domain(domain)
                for ctype in ('crt', 'key', 'csr'):
                    if os.path.exists(fdomain + '.' + ctype):
                        os.remove(pathjoin(self.key_dir, fdomain + '.' + ctype))
        except FileNotFoundError:
            pass
        finally:
            self.prepare()
            
if __name__=='__main__':
    CertManager().generate('example.com')