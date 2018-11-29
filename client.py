import socket
import time
import threading
import signal
import os
import struct
import numpy as np
from precall_protocol import *

def f(a,b):
    global is_exit
    is_exit = 1
    os.kill(os.getpid(),signal.SIGKILL)

def handle_ping(socket, to, seq, ts, payload_len):
    global pong_seq

    socket.sendto(marshall_pong(pong_seq, get_time_stamp(),seq, ts, cur_send_bps, payload_len), to)
    pong_seq += 1

def handle_pong(pong_seq, pong_ts, ping_seq, ts, recv_bps, payload_len):
    global rtt_list
    global bps_list
    global recv_pong_num
    global last_recv_pong_seq

    if recv_bps != -1:
        bps_list.append(recv_bps)
    rtt_list.append(get_time_stamp() - ts)
    recv_pong_num += 1
    last_recv_pong_seq = pong_seq
    
def handle_bw_detect(seq, ts, seq_start, seq_stop, bps, pkt_num, finish_flag, final_target_bps, ul_enabled, dl_enabled, payload_len):
    global recv_len
    global count_seq_stop
    global recv_cnt
    global bwe_list
    global remote_detect_finished

    bwe_list.append(bps)
    recv_len += payload_len
    count_seq_stop = seq
    recv_cnt += 1
    remote_detect_finished = finish_flag

def handle_pong_report(ping_recv_num):
    ul_lr = float(ping_seq - ping_recv_num) / ping_seq
    dl_lr = float(ping_recv_num - pong_recv_num) / ping_recv_num
    print 'ping = %d, ping_recv=%d, pong=%d' % (ping_seq, ping_recv_num, pong_recv_num)
    print 'lossrate: ul=%3.3f, dl=%3.3f, rtt=%dms, bps=%d' % (ul_lr, dl_lr, np.mean(rtt_list), np.mean(bps_list))

def calc_phase_pingpong():
    ullr = float(ping_seq - last_recv_pong_seq) / ping_seq
    dllr = float(last_recv_pong_seq - recv_pong_num) / last_recv_pong_seq
    print 'ullr = %d%%, dllr = %d%%' % (int(ullr * 100), int(dllr * 100))

def recv_thread(client):
    global bwe_list
    global pong_recv_num
    global phase_flag

    while is_exit == 0:
        data, server_addr = client.recvfrom(BUFSIZE)
        ret, result = unmarshall(data)
        if not ret:
            continue

        if result[0] == PING_TYPE:
            # print 'ping', result[0], result[1], result[2]
            handle_ping(client, server_addr, result[1], result[2], len(data))
        elif result[0] == PONG_TYPE:
            # print 'pong', result[0], result[1], result[2], result[3], result[4]
            handle_pong(result[1], result[2], result[3], result[4], result[5], len(data))
            pong_recv_num += 1
        elif result[0] == BW_DETECT_TYPE:
            # print 'bw_detect', result[0], result[1], result[2], result[3], result[4], result[5], result[6], result[7], result[8], result[9], result[10]
            handle_bw_detect(result[1], result[2], result[3], result[4], result[5], result[6], result[7], result[8], result[9], result[10], len(data))
            if phase_flag != PHASE_PING_PONG_RECV_FINISHED:
                calc_phase_pingpong()
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
        # bwe_list.append(int(float(data)))
        # print('client recv: ', data, server_addr)

def send_thread(client, ip_port):
    global payload_len
    global time_interval
    global ping_seq
    global bwd_seq
    global phase_flag

    while is_exit == 0:
        if phase_flag == PHASE_PING_PONG:
            client.sendto(marshall_ping(ping_seq, get_time_stamp(), 64), ip_port)
            ping_seq += 1
            time.sleep(0.01)
            if ping_seq > 200:
                phase_flag = PHASE_PING_PONG_SEND_FINISHED # rampup
        elif phase_flag != PHASE_PING_PONG:
            client.sendto(marshall_bw_detect(bwd_seq, get_time_stamp(), count_seq_start, count_seq_stop, cur_recv_bps, recv_cnt, local_detect_finished, final_target_bps, 1, dl_detect_start, 1400), ip_port)
            bwd_seq += 1
            time.sleep(time_interval)   

def calc_cur_bps(thread_num, time_interval, payload_len):
    cur_send_bps = 1 / time_interval * payload_len * 8 * thread_num
    print 'cur send cur_send_bps: ', cur_send_bps

def get_sender_options(target_bps):
    max_bps_single_thread = 1400 * 8 * 1000
    thread_num = int(target_bps / max_bps_single_thread) + 1
    time_interval = 1 / (target_bps / (1400.0 * 8) / thread_num)
    payload_len = 1400
    # print 'cur sender options: ', thread_num, time_interval, payload_len
    return thread_num, time_interval, payload_len

def sender_thread_ctrl(thread_list, run_thread_num):
    # global th_send_list
    global th_send_alive_list

    # thread_list[0].start()
    alive_num = len(th_send_alive_list)
    # print 'thread num: %d / %d' % (alive_num, run_thread_num) 

    if run_thread_num == alive_num:
        return
    elif run_thread_num > alive_num:
        start_num = run_thread_num - alive_num
        for t in thread_list:
            if not t.isAlive():
                # print 'thread start ...'
                t.start()
                th_send_alive_list.append(t)
                start_num -= 1
                if start_num == 0:
                    break
        if run_thread_num > len(th_send_alive_list):
            print 'Error: Sender thread not enough ...'
    else:
        # todo
        stop_num = alive_num - run_thread_num

def get_bwe_status():
    global bwe_list
    # global bwe_spliter
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

if __name__ == '__main__':
    signal.signal(signal.SIGINT,f)

    PHASE_PING_PONG = 0
    PHASE_PING_PONG_SEND_FINISHED = 1
    PHASE_PING_PONG_RECV_FINISHED = 2

    bwe_list = []
    bwe_spliter = []
    is_exit = 0
    BUFSIZE = 1400
    target_bps = 50000
    pre_target_bps = 0
    payload_len = 1400
    loop_cnt = 0
    time_interval = 0.01
    client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    # ip_port = ('127.0.0.1', 5999)
    ip_port = ('192.168.1.158', 5999)
    th_recv = threading.Thread(target=recv_thread, args=(client, ))
    th_recv.start()
    th_send_list = []
    th_send_alive_list = []
    th_send_run_num = 0
    cur_send_bps = -1
    cur_recv_bps = -1
    pre_recv_len = recv_len = 0
    count_seq_start = count_seq_stop = -1
    recv_cnt = -1
    jitter = -1
    bwe = -1
    ping_seq = 0
    pong_seq = 0
    bwd_seq = 0
    pong_recv_num = 0
    rtt_list = []
    bps_list = []
    phase_flag = PHASE_PING_PONG
    bwd_recv = 0
    recv_pong_num = 0
    last_recv_pong_seq = 0
    bwe_mean_list = []
    bwe_mean_inc_percent = []
    dl_detect_start = 1
    final_target_bps = 5 * 1000 * 1000
    local_detect_finished = 0
    remote_detect_finished = 0

    for i in range(20):
        t = threading.Thread(target=send_thread, args=(client, ip_port, ))
        th_send_list.append(t)

    th_send_list[0].start()
    while is_exit == 0:
        if phase_flag != PHASE_PING_PONG:
            # 1 secs
            if loop_cnt % 10 == 0:
                if local_detect_finished == 0:
                    print 'rampuping ...'
                    target_bps *= 2
                    
                    if target_bps > final_target_bps:
                        print 'Rampup finished .. %dkbps' % final_target_bps
                        target_bps = final_target_bps

                    th_send_run_num, time_interval, payload_len = get_sender_options(target_bps)
                    sender_thread_ctrl(th_send_list, th_send_run_num)
                    # else:
                    #     target_bps = final_target_bps
                    #     th_send_run_num, time_interval, payload_len = get_sender_options(target_bps)
                    #     sender_thread_ctrl(th_send_list, th_send_run_num)
                    #     # bwe_spliter.append([pre_target_bps, len(bwe_list)])
                    #     # get_bwe_status()
                    #     print 'Rampup finished ..'
                    bwe_finished, bwe_bps = get_bwe_status()
                    if bwe_finished:
                        print 'uplink bwe is: %dkbps' % (int(bwe_bps) / 1000)
                        local_detect_finished = 1
                elif remote_detect_finished == 0:
                    print 'sent 100kbps ...'
                    th_send_run_num, time_interval, payload_len = get_sender_options(100 * 1000)
                else:
                    is_exit = 1
                    break
            cur_recv_bps = (recv_len - pre_recv_len) * 8 / 0.1
            # print 'recv start:end=%d:%d, bps=%d, cnt=%d' % (count_seq_start, count_seq_stop, cur_recv_bps, recv_cnt)

            pre_recv_len = recv_len
            count_seq_start = count_seq_stop
            recv_cnt = 0

        time.sleep(0.1)
        loop_cnt += 1

    # client.close()

    # client.sendto(marshall_ping(0, get_time_stamp()), ip_port)
    # client.sendto(marshall_pong(1234, 5678), ip_port)
    # client.sendto(marshall_report(0, 1, 2), ip_port)
    # client.sendto(marshall_report_ack(), ip_port)
    # client.sendto(marshall_bw_detect(12, 23, 34, 45, 56, 67, 1400), ip_port)
    th_recv.join()
    # client.close()
