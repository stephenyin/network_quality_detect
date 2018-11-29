import struct
import time

magic_num = 5555
PING_TYPE = 0
PONG_TYPE = 1
BW_DETECT_TYPE = 2
REPORT_TYPE = 3
REPORT_ACK_TYPE = 4
PONG_REPORT = 5
PONG_REPORT_ACK = 5


def get_time_stamp(): 
    ct = time.time() 
    local_time = time.localtime(ct) 
    data_head = time.strftime("%Y-%m-%d %H:%M:%S", local_time) 
    data_secs = (ct - int(ct)) * 1000 
    time_stamp = "%s.%03d" % (data_head, data_secs) 
    stamp = ("".join(time_stamp.split()[0].split("-"))+"".join(time_stamp.split()[1].split(":"))).replace('.', '') 
    return int(stamp) % 1000000
    # print(stamp)

def marshall_ping(ping_seq, ping_ts, payload_len):
    pad_len = payload_len - 4
    return struct.pack('iiii%ds' % pad_len, magic_num, PING_TYPE, ping_seq, ping_ts, ''.zfill(pad_len))

def marshall_pong(pong_seq, pong_ts, ping_seq, ping_ts, recv_bps, payload_len):
    pad_len = payload_len - 5
    return struct.pack('iiiiiii%ds' % pad_len, magic_num, PONG_TYPE, pong_seq, pong_ts, ping_seq, ping_ts, recv_bps, ''.zfill(pad_len))

def marshall_bw_detect(seq, ts, seq_start, seq_end, bps, pkt_num, finish_flag, final_target_bps, ul_enabled, dl_enabled, payload_len):
    pad_len = payload_len - 48
    return struct.pack('iiiiiiiiiiii%ds' % pad_len, magic_num, BW_DETECT_TYPE, seq, ts, seq_start, seq_end, bps, pkt_num, finish_flag, final_target_bps, ul_enabled, dl_enabled, ''.zfill(pad_len))

def marshall_report(lossrate, jitter, bandwidth):
    return struct.pack('iiiii', magic_num, REPORT_TYPE, lossrate, jitter, bandwidth)

def marshall_report_ack():
    return struct.pack('ii', magic_num, REPORT_ACK_TYPE)

def marshall_pong_report(ping_recv_num):
    return struct.pack('iii', magic_num, PONG_REPORT, ping_recv_num)

def marshall_pong_report_ack():
    return struct.pack('ii', magic_num, PONG_REPORT_ACK)

def unmarshall(data):
    if len(data) < 8:
        return False, None

    magic, msg_type = struct.unpack('<ii', data[:8])
    if magic != magic_num:
        return False, None
    
    p = data[8:]
    offset = 0
    if msg_type == PING_TYPE:
        seq = struct.unpack_from('<i', p, offset)
        offset += 4
        ts = struct.unpack_from('<i', p, offset)
        return True, (msg_type, seq[0], ts[0])
    elif msg_type == PONG_TYPE:
        pong_seq = struct.unpack_from('<i', p, offset)
        offset += 4
        pong_ts = struct.unpack_from('<i', p, offset)
        offset += 4
        ping_seq = struct.unpack_from('<i', p, offset)
        offset += 4
        ts = struct.unpack_from('<i', p, offset)
        offset += 4
        bps = struct.unpack_from('<i', p, offset)
        return True, (msg_type, pong_seq[0], pong_ts[0], ping_seq[0], ts[0], bps[0])
    elif msg_type == BW_DETECT_TYPE:
        seq = struct.unpack_from('<i', p, offset)
        offset += 4
        ts = struct.unpack_from('<i', p, offset)
        offset += 4
        seq_start = struct.unpack_from('<i', p, offset)
        offset += 4
        seq_end = struct.unpack_from('<i', p, offset)
        offset += 4
        bps = struct.unpack_from('<i', p, offset)
        offset += 4
        recv_num = struct.unpack_from('<i', p, offset)
        offset += 4
        finish_flag = struct.unpack_from('<i', p, offset)
        offset += 4
        final_target_bps = struct.unpack_from('<i', p, offset)
        offset += 4
        ul_enabled = struct.unpack_from('<i', p, offset)
        offset += 4
        dl_enabled = struct.unpack_from('<i', p, offset)
        return True, (msg_type, seq[0], ts[0], seq_start[0], seq_end[0], bps[0], recv_num[0], finish_flag[0], final_target_bps[0], ul_enabled[0], dl_enabled[0])
    elif msg_type == REPORT_TYPE:
        lossrate = struct.unpack_from('<i', p, offset)
        offset += 4
        jitter = struct.unpack_from('<i', p, offset)
        offset += 4
        bandwidth = struct.unpack_from('<i', p, offset)
        return True, (msg_type, lossrate[0], jitter[0], bandwidth[0])
    elif msg_type == REPORT_ACK_TYPE:
        return True, (msg_type, )
    elif msg_type == PONG_REPORT:
        ping_recv_num = struct.unpack_from('<i', p,  offset)
        return True, (msg_type, ping_recv_num[0])
    elif msg_type == PONG_REPORT_ACK:
        return True, (msg_type, )
    else:
        print 'Error: unknown msg_type %d' % msg_type
        return False, None