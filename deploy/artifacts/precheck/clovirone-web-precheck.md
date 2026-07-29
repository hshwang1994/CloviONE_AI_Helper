# ClovirONE Web Assistant — 사전조사 보고서

생성: 00-precheck.sh (읽기 전용). 비밀번호/토큰/키 값은 포함되지 않습니다.

## 판정
- **진행 가능**

## 시스템
```
 Static hostname: ai-n8n-svr
       Icon name: computer-vm
         Chassis: vm 🖴
      Machine ID: 025c6ee8e577477980228274f6813c5d
         Boot ID: b131d2efe9994ceeb21c45c718312998
  Virtualization: vmware
Operating System: Ubuntu 24.04.2 LTS
          Kernel: Linux 6.8.0-134-generic
    Architecture: x86-64
 Hardware Vendor: VMware, Inc.
  Hardware Model: VMware Virtual Platform
Firmware Version: 6.00
   Firmware Date: Thu 2020-11-12
    Firmware Age: 5y 8month
Linux ai-n8n-svr 6.8.0-134-generic #134-Ubuntu SMP PREEMPT_DYNAMIC Fri Jun 26 18:43:11 UTC 2026 x86_64 x86_64 x86_64 GNU/Linux
python3: Python 3.12.3
nproc: 4  mem_available_kb: 6868524
```
## 네트워크 / DNS
```
lo               UNKNOWN        127.0.0.1/8 ::1/128 
ens160           UP             10.100.64.71/24 fe80::250:56ff:fe84:2a2d/64 
getent clovirone-ai.gooddi.lab -> 10.100.64.71 (expected 10.100.64.71)
```
## 용량
```
Filesystem                         Size  Used Avail Use% Mounted on
tmpfs                              795M  1.3M  793M   1% /run
/dev/mapper/ubuntu--vg-ubuntu--lv   48G   12G   35G  25% /
tmpfs                              3.9G     0  3.9G   0% /dev/shm
tmpfs                              5.0M     0  5.0M   0% /run/lock
/dev/sda2                          2.0G  104M  1.7G   6% /boot
tmpfs                              795M   12K  795M   1% /run/user/0
tmpfs                              795M   12K  795M   1% /run/user/1000

               total        used        free      shared  buff/cache   available
Mem:           7.8Gi       1.2Gi       848Mi       1.2Mi       6.0Gi       6.6Gi
Swap:          4.0Gi          0B       4.0Gi
```
## 리스닝 포트 (관심 대상)
```
80    (free)
443   (free)
8080  (free)
5678  LISTEN 0      511        127.0.0.1:5678      0.0.0.0:*    users:(("node",pid=4300,fd=22))                        
8787  LISTEN 0      5          127.0.0.1:8787      0.0.0.0:*    users:(("python3",pid=17003,fd=3))                     
8788  LISTEN 0      5          127.0.0.1:8788      0.0.0.0:*    users:(("python3",pid=17978,fd=3))                     
8789  LISTEN 0      5          127.0.0.1:8789      0.0.0.0:*    users:(("python3",pid=24435,fd=3))                     
```
## 기존 서비스
```
claude-request-interpreter.service           enabled         enabled
claude-ticket-runner.service                 enabled         enabled
claude-work-assistant.service                enabled         enabled
n8n.service                                  enabled         enabled

failed units:
  UNIT LOAD ACTIVE SUB DESCRIPTION

0 loaded units listed.
```
## Nginx
```
```
## TLS 인증서 (공개 정보)
- `/etc/ssl/certs/GlobalSign_ECC_Root_CA_-_R5.pem`: subject=OU = GlobalSign ECC Root CA - R5, O = GlobalSign, CN = GlobalSign notAfter=Jan 19 03:14:07 2038 GMT 
- `/etc/ssl/certs/T-TeleSec_GlobalRoot_Class_3.pem`: subject=C = DE, O = T-Systems Enterprise Services GmbH, OU = T-Systems Trust Center, CN = T-TeleSec GlobalRoot Class 3 notAfter=Oct  1 23:59:59 2033 GMT 
- `/etc/ssl/certs/DigiCert_Global_Root_G3.pem`: subject=C = US, O = DigiCert Inc, OU = www.digicert.com, CN = DigiCert Global Root G3 notAfter=Jan 15 12:00:00 2038 GMT 
- `/etc/ssl/certs/Go_Daddy_Root_Certificate_Authority_-_G2.pem`: subject=C = US, ST = Arizona, L = Scottsdale, O = "GoDaddy.com, Inc.", CN = Go Daddy Root Certificate Authority - G2 notAfter=Dec 31 23:59:59 2037 GMT 
- `/etc/ssl/certs/SSL.com_EV_Root_Certification_Authority_RSA_R2.pem`: subject=C = US, ST = Texas, L = Houston, O = SSL Corporation, CN = SSL.com EV Root Certification Authority RSA R2 notAfter=May 30 18:14:37 2042 GMT 
- `/etc/ssl/certs/Hellenic_Academic_and_Research_Institutions_RootCA_2015.pem`: subject=C = GR, L = Athens, O = Hellenic Academic and Research Institutions Cert. Authority, CN = Hellenic Academic and Research Institutions RootCA 2015 notAfter=Jun 30 10:11:21 2040 GMT 
- `/etc/ssl/certs/emSign_Root_CA_-_C1.pem`: subject=C = US, OU = emSign PKI, O = eMudhra Inc, CN = emSign Root CA - C1 notAfter=Feb 18 18:30:00 2043 GMT 
- `/etc/ssl/certs/SSL.com_TLS_ECC_Root_CA_2022.pem`: subject=C = US, O = SSL Corporation, CN = SSL.com TLS ECC Root CA 2022 notAfter=Aug 19 16:33:47 2046 GMT 
- `/etc/ssl/certs/emSign_Root_CA_-_G1.pem`: subject=C = IN, OU = emSign PKI, O = eMudhra Technologies Limited, CN = emSign Root CA - G1 notAfter=Feb 18 18:30:00 2043 GMT 
- `/etc/ssl/certs/DigiCert_TLS_ECC_P384_Root_G5.pem`: subject=C = US, O = "DigiCert, Inc.", CN = DigiCert TLS ECC P384 Root G5 notAfter=Jan 14 23:59:59 2046 GMT 
- `/etc/ssl/certs/D-TRUST_BR_Root_CA_2_2023.pem`: subject=C = DE, O = D-Trust GmbH, CN = D-TRUST BR Root CA 2 2023 notAfter=May  9 08:56:30 2038 GMT 
- `/etc/ssl/certs/HiPKI_Root_CA_-_G1.pem`: subject=C = TW, O = "Chunghwa Telecom Co., Ltd.", CN = HiPKI Root CA - G1 notAfter=Dec 31 15:59:59 2037 GMT 
- `/etc/ssl/certs/TWCA_CYBER_Root_CA.pem`: subject=C = TW, O = TAIWAN-CA, OU = Root CA, CN = TWCA CYBER Root CA notAfter=Nov 22 15:59:59 2047 GMT 
- `/etc/ssl/certs/COMODO_ECC_Certification_Authority.pem`: subject=C = GB, ST = Greater Manchester, L = Salford, O = COMODO CA Limited, CN = COMODO ECC Certification Authority notAfter=Jan 18 23:59:59 2038 GMT 
- `/etc/ssl/certs/Microsoft_ECC_Root_Certificate_Authority_2017.pem`: subject=C = US, O = Microsoft Corporation, CN = Microsoft ECC Root Certificate Authority 2017 notAfter=Jul 18 23:16:04 2042 GMT 
- `/etc/ssl/certs/Amazon_Root_CA_2.pem`: subject=C = US, O = Amazon, CN = Amazon Root CA 2 notAfter=May 26 00:00:00 2040 GMT 
- `/etc/ssl/certs/NAVER_Global_Root_Certification_Authority.pem`: subject=C = KR, O = NAVER BUSINESS PLATFORM Corp., CN = NAVER Global Root Certification Authority notAfter=Aug 18 23:59:59 2037 GMT 
- `/etc/ssl/certs/Certainly_Root_E1.pem`: subject=C = US, O = Certainly, CN = Certainly Root E1 notAfter=Apr  1 00:00:00 2046 GMT 
- `/etc/ssl/certs/ANF_Secure_Server_Root_CA.pem`: subject=serialNumber = G63287510, C = ES, O = ANF Autoridad de Certificacion, OU = ANF CA Raiz, CN = ANF Secure Server Root CA notAfter=Aug 30 10:00:38 2039 GMT 
- `/etc/ssl/certs/Atos_TrustedRoot_2011.pem`: subject=CN = Atos TrustedRoot 2011, O = Atos, C = DE notAfter=Dec 31 23:59:59 2030 GMT 

## 방화벽
```
Status: inactive
```
## 인터넷 의존성
```
PyPI reachable: true (HTTP/2 200 )
apt install simulation ok: false
```
## 기존 clovirone-web 설치 흔적
```
existing_install: false
clovirone-web user: absent
```
