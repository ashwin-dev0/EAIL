from cryptography.fernet import Fernet
if __name__=='__main__':
    print('OAuth cache key (store privately as ZOHO_TOKEN_CACHE_KEY):')
    print(Fernet.generate_key().decode())
