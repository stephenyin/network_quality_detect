import socket
import time
import threading
import struct
import signal
import os
import numpy as np
from precall_protocol import *

def f(a,b):
    global is_exit
    is_exit = 1
    os.kill(os.getpid(),signal.SIGKILL)

def handle_ping(socket, to, seq, ts, payload_len):
    global recv_len
    global pong_seq

    recv_len += payload_len
    socket.sendto(marshall_pong(pong_seq, get_time_stamp(), seq, ts, cur_recv_bps, payload_len), to)
    pong_seq += 1

# def handle_pong(pong_seq, pong_ts, ping_seq, ts, bps, payload_len):
#     print 'Rtt = ', get_time_stamp() - ts

# def handle_pong_report(ping_recv_num):
#     pass

def handle_bw_detect(seq, ts, seq_start, seq_stop, bps, pkt_num, finish_flag, target_bps, ul_enabled, dl_enabled, payload_len):
    global recv_len
    global count_seq_stop
    global recv_cnt
    global dl_detect_start
    global final_target_bps
    global remote_detect_finished

    recv_len += payload_len
    count_seq_stop = seq
    recv_cnt += 1
    dl_detect_start = ul_enabled
    final_target_bps = target_bps
    remote_detect_finished = finish_flag
    bwe_list.append(bps)

def worker_thread():
    global cur_recv_bps
    global pre_recv_len
    global count_seq_start
    global recv_cnt
    global th_send_run_num 
    global time_interval
    global target_bps
    global payload_len
    global is_exit
    global local_detect_finished
    
    loop_cnt = 0
    
    while is_exit == 0:
        if ping_recv_num == 0:
            continue

        cur_recv_bps = (recv_len - pre_recv_len) * 8 / 0.1
        # print 'recv start:end=%d:%d, bps=%d, cnt=%d' % (count_seq_start, count_seq_stop, cur_recv_bps, recv_cnt)

        pre_recv_len = recv_len
        count_seq_start = count_seq_stop
        recv_cnt = 0
        
        if loop_cnt % 10 == 0 and phase_flag != PHASE_PING_PONG:
            if remote_detect_finished != 0:
                if dl_detect_start != 0:
                    print 'rampuping ...'
                    # Downlink bw detect
                    target_bps *= 2
                    if target_bps > final_target_bps:
                        print 'Rampup finished .. %dkbps' % final_target_bps
                        target_bps = final_target_bps
                    th_send_run_num, time_interval, payload_len = get_sender_options(target_bps)
                    sender_thread_ctrl(th_send_list, th_send_run_num)
                    bwe_finished, bwe_bps = get_bwe_status()
                    if bwe_finished:
                        print 'Downlink bwe is: %dkbps' % (int(bwe_bps) / 1000)
                        local_detect_finished = 1

                        # Waiting to notify remote detecting is finished
                        time.sleep(1)

                        is_exit = 1
                        break
                else:
                    # All done
                    is_exit = 1
                    break
            else:
                print 'sent 100kbps'
                th_send_run_num, time_interval, payload_len = get_sender_options(100 * 1000)
                # sender_thread_ctrl(th_send_list, th_send_run_num)
        loop_cnt += 1
        time.sleep(0.1)
        

def send_thread(client, ip_port):
    global bwd_seq
    global local_detect_finished

    while is_exit == 0:
        if phase_flag != PHASE_PING_PONG:
            client.sendto(marshall_bw_detect(bwd_seq, get_time_stamp(), count_seq_start, count_seq_stop, cur_recv_bps, recv_cnt, local_detect_finished, -1, -1, -1, 1400), ip_port)
            bwd_seq += 1
            time.sleep(time_interval)

def get_bwe_status():
    global bwe_list
    global bwe_mean_list
    global bwe_mean_inc_percent

    bwe_mean_list.append(int(np.mean(bwe_list)))
    # print 'bwe mean list: ', bwe_mean_list
    if len(bwe_mean_list) > 1:
        factor = float(bwe_mean_list[-1] - bwe_mean_list[-2]) / bwe_mean_list[-2]
        bwe_mean_inc_percent.append(factor)
        # print 'factor: %3.3f' % factor
    
    if len(bwe_mean_inc_percent) > 1:
        if bwe_mean_inc_percent[-1] < 0.1 and bwe_mean_inc_percent[-2] < 0.1:
            return True, bwe_mean_list[-1]
    bwe_list = []

    return False, None

def get_sender_options(target_bps):
    max_bps_single_thread = 1400 * 8 * 1000
    thread_num = int(target_bps / max_bps_single_thread) + 1
    time_interval = 1 / (target_bps / (1400.0 * 8) / thread_num)
    payload_len = 1400
    # print 'cur sender options: ', thread_num, time_interval, payload_len
    return thread_num, time_interval, payload_len

def sender_thread_ctrl(thread_list, run_thread_num):
    global th_send_alive_list

    alive_num = len(th_send_alive_list)

    if run_thread_num == alive_num:
        return
    elif run_thread_num > alive_num:
        start_num = run_thread_num - alive_num
        for t in thread_list:
            if not t.isAlive():
                t.start()
                th_send_alive_list.append(t)
                start_num -= 1
                if start_num == 0:
                    break
        if run_thread_num > len(th_send_alive_list):
            print 'Error: Sender thread not enough ...'
    else:
        # todo reduce thread num
        stop_num = alive_num - run_thread_num

if __name__ == '__main__':
    is_exit = 0
    signal.signal(signal.SIGINT,f)

    BUFSIZE = 1400
    PHASE_PING_PONG = 0
    PHASE_PING_PONG_SEND_FINISHED = 1
    PHASE_PING_PONG_RECV_FINISHED = 2

    ip_port = ('127.0.0.1', 5999)
    server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server.bind(ip_port)
    pre_report = pre = now = 0
    pre_recv_len = recv_len = 0
    ping_recv_num = 0
    phase_flag = PHASE_PING_PONG
    pong_seq = 0
    thread_send = None
    thread_worker = None
    bwd_seq = 0
    cur_recv_bps = 0
    count_seq_start = count_seq_stop = -1
    recv_cnt = -1
    th_send_run_num = 0 
    time_interval = 0
    payload_len = 1400
    target_bps = 50 * 1000
    dl_detect_start = 0
    final_target_bps = 5 * 1000 * 1000
    remote_detect_finished = 0
    local_detect_finished = 0
    bwe_list = []
    bwe_mean_list = []
    bwe_mean_inc_percent = []
    th_send_list = []
    th_send_alive_list = []
    th_send_run_num = 0

    thread_worker = threading.Thread(target=worker_thread, args=())
    thread_worker.start()

    while is_exit == 0:
        data, client_addr = server.recvfrom(BUFSIZE)
        ret, result = unmarshall(data)
        if not ret:
            continue
            
        if result[0] == PING_TYPE:
            handle_ping(server, client_addr, result[1], result[2], len(data))
            ping_recv_num += 1
        elif result[0] == PONG_TYPE:
            pass
            # handle_pong(result[1], result[2], result[3], result[4], result[5], len(data))
        elif result[0] == BW_DETECT_TYPE:
            handle_bw_detect(result[1], result[2], result[3], result[4], result[5], result[6], result[7], result[8], result[9], result[10], len(data))

            # Prepare threads
            if len(th_send_list) == 0:
                for i in range(20):
                    t = threading.Thread(target=send_thread, args=(server, client_addr, ))
                    th_send_list.append(t)
                th_send_list[0].start()
            phase_flag = PHASE_PING_PONG_RECV_FINISHED
        # elif result[0] == REPORT_TYPE:
        #     print 'report', result[0], result[1], result[2], result[3]
        # elif result[0] == REPORT_ACK_TYPE:
        #     print 'report_ack', result[0]
        # elif result[0] == PONG_REPORT:
        #     print 'pong_report', result[0], result[1]
        #     handle_pong_report(result[1])
        # elif result[0] == PONG_REPORT_ACK:
        #     print 'pong_report_ack', result[0]
        else:
            print 'Unknown msg %d' % result[0]
        
    server.close()