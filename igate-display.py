import serial
import time
import psutil
import os
import datetime
import socket
import subprocess

# Função para converter latitude/longitude em grid locator
def latlon_to_grid(lat, lon):
    UPPERCASE_A_ASCII = ord('A')
    
    # Ajustando latitude e longitude
    lon += 180
    lat += 90
    
    # Calculando os componentes do grid
    A = chr(UPPERCASE_A_ASCII + int(lon / 20))
    B = chr(UPPERCASE_A_ASCII + int(lat / 10))
    
    lon_remainder = lon % 20
    lat_remainder = lat % 10
    
    C = str(int(lon_remainder / 2))
    D = str(int(lat_remainder))
    
    lon_remainder = (lon_remainder % 2) * 60
    lat_remainder = (lat_remainder % 1) * 60
    
    E = chr(UPPERCASE_A_ASCII + int(lon_remainder / 5))
    F = chr(UPPERCASE_A_ASCII + int(lat_remainder / 2.5))
    
    return A + B + C + D + E + F

# Função para ler MYCALL do arquivo de configuração
def read_mycall(config_file):
    try:
        with open(config_file, 'r') as f:
            for _ in range(40):  # Limita a leitura às primeiras 40 linhas
                line = f.readline()
                if line.startswith('MYCALL'):
                    return line.split()[1].strip()
    except Exception as e:
        print(f"Erro ao ler MYCALL: {e}")
    return None

# Função para atualizar variáveis com as informações extraídas
def update_variables(log_entry, mycall):
    latitude = log_entry[10].strip()
    longitude = log_entry[11].strip()

    estacao_ouvinte = log_entry[4]
    estacao_transmissora = log_entry[3]
    origem = "RF" if log_entry[7] == '!' else "IG"

    if origem == "RF" and estacao_ouvinte == estacao_transmissora:
        estacao_ouvinte = mycall

    gridlocator = latlon_to_grid(float(latitude), float(longitude)) if latitude and longitude else "N/A"

    variables = {
        "estacao_transmissora": estacao_transmissora,
        "estacao_ouvinte": estacao_ouvinte,
        "intensidade_sinal": log_entry[5],
        "latitude": latitude if latitude else "N/A",
        "longitude": longitude if longitude else "N/A",
        "velocidade": log_entry[12],
        "gridlocator": gridlocator,
        "origem": origem,
        "comment": log_entry[-1]
    }
    return variables

# Função para enviar dados pela serial
def send_serial(ser, cmd, value):
    data = bytes([0xFF, 0xFF, 0xFF]) + f'{cmd}="{value}"'.encode() + bytes([0xFF, 0xFF, 0xFF])
    ser.write(data)

# Função para obter temperatura
def get_temperature():
    try:
        with open('/sys/class/thermal/thermal_zone0/temp', 'r') as f:
            temp_raw = f.read().strip()
        temp = int(temp_raw) / 1000.0
        return f"Temp: {temp:.1f}'C"
    except Exception as e:
        return "Temp: N/A"

# Função para obter uso da CPU
def get_cpu_usage():
    return f"CPU: {psutil.cpu_percent()}%"

# Função para obter uso do HD
def get_hd_usage():
    usage = psutil.disk_usage('/')
    return f"HD: {usage.percent}%"

# Função para obter IP da VPN
def get_ip_vpn():
    try:
        addrs = psutil.net_if_addrs()
        if 'tun0' in addrs:
            for addr in addrs['tun0']:
                if addr.family == socket.AF_INET:
                    return f"tun0: {addr.address}"
        return "tun0: offline"
    except Exception as e:
        return "tun0: offline"

# Função para obter IP da LAN
def get_ip_lan():
    try:
        addrs = psutil.net_if_addrs()
        if 'wlan0' in addrs:
            for addr in addrs['wlan0']:
                if addr.family == socket.AF_INET:
                    return f"wlan0: {addr.address}"
        elif 'eth0' in addrs:
            for addr in addrs['eth0']:
                if addr.family == socket.AF_INET:
                    return f"eth0: {addr.address}"
        return "eth0: offline"
    except Exception as e:
        return "eth0: offline"

# Função para obter status do serviço direwolf
def get_direwolf_status():
    try:
        result = subprocess.run(['systemctl', 'is-active', 'aprs-direwolf.service'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return "online" if result.stdout.strip() == b'active' else "offline"
    except Exception as e:
        return "offline"

# Função principal para ler o log e enviar dados pela serial
def main():
    ser = serial.Serial('/dev/serial0', 115200, timeout=1)
    ser.flush()

    # Ler MYCALL do arquivo de configuração
    mycall = read_mycall('/etc/direwolf/direwolf.conf')
    if not mycall:
        print("Não foi possível ler MYCALL do arquivo de configuração.")
        return

    # Enviar valor fixo uma vez
    send_serial(ser, "t3.txt", "PY2PCR-15")
    
    direwolf_check_interval = 10  # Intervalo de verificação do serviço direwolf em segundos
    last_direwolf_check = 0
    
    # Leitura contínua do log
    while True:
        with open('/var/log/direwolf/direwolf.log', 'rb') as f:
            lines = f.readlines()[-4:]  # Lê as últimas 4 linhas

        for i in range(len(lines)):
            lines[i] = lines[i].decode('utf-8', errors='ignore')
        
        variables_list = [update_variables(line.split(','), mycall) for line in lines if len(line.split(',')) > 17]

        if len(variables_list) >= 1:
            var = variables_list[-1]
            send_serial(ser, "g0.txt", var["comment"])
            send_serial(ser, "t4.txt", var["estacao_transmissora"])
            send_serial(ser, "t5.txt", var["estacao_ouvinte"])
            send_serial(ser, "t25.txt", var["origem"])
            send_serial(ser, "t17.txt", var["latitude"])
            send_serial(ser, "t18.txt", var["longitude"])
            send_serial(ser, "t22.txt", var["velocidade"])
            send_serial(ser, "t21.txt", var["gridlocator"])
            send_serial(ser, "t13.txt", var["intensidade_sinal"])

        if len(variables_list) >= 2:
            var = variables_list[-2]
            send_serial(ser, "g1.txt", var["comment"])
            send_serial(ser, "t6.txt", var["estacao_transmissora"])
            send_serial(ser, "t7.txt", var["estacao_ouvinte"])
            send_serial(ser, "t26.txt", var["origem"])

        if len(variables_list) >= 3:
            var = variables_list[-3]
            send_serial(ser, "g2.txt", var["comment"])
            send_serial(ser, "t8.txt", var["estacao_transmissora"])
            send_serial(ser, "t9.txt", var["estacao_ouvinte"])
            send_serial(ser, "t27.txt", var["origem"])

        if len(variables_list) >= 4:
            var = variables_list[-4]
            send_serial(ser, "g3.txt", var["comment"])
            send_serial(ser, "t10.txt", var["estacao_transmissora"])
            send_serial(ser, "t11.txt", var["estacao_ouvinte"])
            send_serial(ser, "t28.txt", var["origem"])

        # Enviar atualizações periódicas
        current_time = datetime.datetime.now()
        send_serial(ser, "t14.txt", current_time.strftime("%H:%M - %d/%m/%Y"))

        send_serial(ser, "t15.txt", get_temperature())
        send_serial(ser, "t16.txt", get_cpu_usage())
        send_serial(ser, "t29.txt", get_hd_usage())
        send_serial(ser, "t0.txt", get_ip_vpn())
        send_serial(ser, "t1.txt", get_ip_lan())
        send_serial(ser, "t3.txt", mycall)

        # Verifica o status do serviço direwolf a cada 10 segundos
        if time.time() - last_direwolf_check > direwolf_check_interval:
            send_serial(ser, "t2.txt", get_direwolf_status())
            last_direwolf_check = time.time()

        time.sleep(5)

if __name__ == "__main__":
    main()
