#!/usr/bin/env python

from main import PKT_DIR_INCOMING, PKT_DIR_OUTGOING

import struct
import socket

# TODO: Feel free to import any Python standard moduless as necessary.
# (http://docs.python.org/2/library/)
# You must NOT use any 3rd-party libraries.

class Firewall:
    def __init__(self, config, iface_int, iface_ext):
        self.iface_int = iface_int
        self.iface_ext = iface_ext

        self.debug = False

        self.ipv4ProHash = {1:'icmp', 6:'tcp', 17:'udp'}
        
        self.RawRules = []
        with open(config['rule']) as f:
            self.RawRules = f.readlines()
        self.rules = []     # store only valid rules
        for rule in self.RawRules:
            rule = rule.rstrip().split()
            rule = [r.lower() for r in rule]
            if len(rule)<3:
                continue
            if rule[0]=="drop" or rule[0]=="pass":
                if rule[1]=="dns" and len(rule)==3:
                    if "*" not in rule[2] or ("*" in rule[2] and rule[2][0]=="*"):
                        rule[2] = rule[2].lower()  # covert all domain names into lower case
                        self.rules.append(rule)
                else:
                    if len(rule)!=4:
                        continue
                    self.rules.append(rule)

        if self.debug:
            for i in self.rules:
                print i
                print "Initialization finished"
                
        # Load the GeoIP DB
        self.geoDb = []
        with open('geoipdb.txt') as f:
            self.geoDb = f.readlines()
        self.geoDb = [(entry.rstrip()).split() for entry in self.geoDb if entry.rstrip()!=""]


    # @pkt_dir: either PKT_DIR_INCOMING or PKT_DIR_OUTGOING
    # @pkt: the actual data of the IPv4 packet (including IP header)
    def handle_packet(self, pkt_dir, pkt):
        # Parse the pkt
        ## TODO: need to use socket.htons/socket.ntohs to convert endians
        pkt_info = {'ip_protocal':'', 'external_ip':'', 'external_port':''}
        pkt_info['ip_protocal'] = struct.unpack('!B', pkt[9])[0]

        ip_version =  struct.unpack('!B', pkt[0])[0] >> 4
        ip_header_len =  (struct.unpack('!B', pkt[0])[0] & 15) * 4
        # ip_header_len =  struct.unpack('!B', pkt[0])[0] & 7


        if self.debug:
            print "header version is", ip_version, "and header length is", ip_header_len
            print "the total length of packet is ", struct.unpack('!H', pkt[2:4])
        
        source_addr = self.intToDotQuad(struct.unpack('!L', pkt[12:16])[0])
        dest_addr = self.intToDotQuad(struct.unpack('!L', pkt[16:20])[0])

        if pkt_info['ip_protocal'] == 6 or pkt_info['ip_protocal']==17:

           
            source_port = struct.unpack('!H', pkt[ip_header_len:ip_header_len + 2])[0]
            dest_port = struct.unpack('!H', pkt[ip_header_len + 2:ip_header_len + 4])[0]

            if pkt_info['ip_protocal'] == 6:
                if self.debug:
                    print "-------------------------TCP"
                    print "source ip address is", source_addr
                    print "destination ip address is", dest_addr
                    print "source port is", source_port
                    print "destination port is", dest_port

                if pkt_dir == PKT_DIR_INCOMING:
                    if self.debug:
                        print "incoming packet"
                    pkt_info['external_port'] = source_port
                    pkt_info['external_ip'] = source_addr
                    matchRes = self.proIpPortMatching(pkt_info)
                    if self.debug:
                        print "+++++++++++++++++++incoming packet rule matching result says,", matchRes
                    if matchRes == "pass":
                        print "SENT"
                        self.iface_int.send_ip_packet(pkt)
                else:
                    if self.debug:
                        print "outgoing packet"
                    pkt_info['external_port'] = dest_port
                    pkt_info['external_ip'] = dest_addr
                    matchRes = self.proIpPortMatching(pkt_info)
                    if self.debug:
                        print "+++++++++++++++++++outgoing packet rule matching result says,", matchRes
                    if matchRes == "pass":
                        print "SENT"
                        self.iface_ext.send_ip_packet(pkt)
            else:
                if self.debug:
                    print "-----------------------------UDP"
                    print "source ip address is", source_addr
                    print "destination ip address is", dest_addr
                    print "source port is", source_port
                    print "destination port is", dest_port
                if pkt_dir==PKT_DIR_OUTGOING and dest_port==53:     # treat only the udp portion of the pkt as the argument
                    dnsQueryBool, dnsName = self.checkDnsQuery(pkt[ip_header_len:])
                    pkt_info['external_port'] = dest_port
                    pkt_info['external_ip'] = dest_addr
                    if not dnsQueryBool:
                        if self.debug:
                            print "Normal UDP with port=53 and OUTGOING"
                        matchRes = self.proIpPortMatching(pkt_info)
                        if self.debug:
                            print "+++++++++++++++++++outgoing packet rule matching result says,", matchRes
                        if matchRes == "pass":
                            print "SENT"
                            self.iface_ext.send_ip_packet(pkt)
                    else:
                        if self.debug:
                            print "DNS query packet"
                        ## do something here
                        dns_matching_result = self.dnsMatching(dnsName, pkt_info)
                        if dns_matching_result=="pass" or dns_matching_result=="no-match":
                            print "SENT"
                            self.iface_ext.send_ip_packet(pkt)
                        else:   # dns_matching_result=="drop":
                            if self.debug:
                                print "DROPPING DNS QUERY MATCHED"
                else:
                    if self.debug:
                        print "Normal UDP"

                    if pkt_dir == PKT_DIR_INCOMING:
                        if self.debug:
                            print "incoming packet"
                        pkt_info['external_port'] = source_port
                        pkt_info['external_ip'] = source_addr
                        matchRes = self.proIpPortMatching(pkt_info)
                        if self.debug:
                            print "+++++++++++++++++++incoming packet rule matching result says,", matchRes
                        if matchRes == "pass":
                            print "SENT"
                            self.iface_int.send_ip_packet(pkt)
                    else:
                        if self.debug:
                            print "outgoing packet"
                        pkt_info['external_port'] = dest_port
                        pkt_info['external_ip'] = dest_addr
                        matchRes = self.proIpPortMatching(pkt_info)
                        if self.debug:
                            print "+++++++++++++++++++outgoing packet rule matching result says,", matchRes
                        if matchRes == "pass":
                            print "SENT"
                            self.iface_ext.send_ip_packet(pkt)

        elif pkt_info['ip_protocal'] == 1:
            icmp_type = struct.unpack('!B', pkt[ip_header_len])[0]
            if self.debug:
                print "icmp_type is", icmp_type
            pkt_info['external_port'] = icmp_type
            if pkt_dir == PKT_DIR_INCOMING:
                if self.debug:
                    print "incoming packet"
                pkt_info['external_ip'] = source_addr
                matchRes = self.proIpPortMatching(pkt_info)
                if self.debug:
                    print "+++++++++++++++++++incoming packet rule matching result says,", matchRes
                if matchRes == "pass":
                    print "SENT"
                    self.iface_int.send_ip_packet(pkt)
            else:
                if self.debug:
                    print "outgoing packet"
                pkt_info['external_ip'] = dest_addr
                matchRes = self.proIpPortMatching(pkt_info)
                if self.debug:
                    print "+++++++++++++++++++outgoing packet rule matching result says,", matchRes
                if matchRes == "pass":
                    print "SENT"
                    self.iface_ext.send_ip_packet(pkt)
        else:
            if self.debug:
                print "The potocal is", pkt_info['ip_protocal']
            if pkt_dir == PKT_DIR_OUTGOING:
                print "SENT"
                self.iface_ext.send_ip_packet(pkt)
            else:
                print "SENT"
                self.iface_int.send_ip_packet(pkt)

    def intToDotQuad(self, addr):
        dot_quad = []
        for i in range(4):
            dot_quad.append(addr % 256)
            addr = addr >> 8
        return list(reversed(dot_quad))

    def dotQuadToInt(self, quad):
        num = 0
        for i in quad:
            num += int(i)
            num = num << 8
        num = num >> 8
        return num

    def isInCountry(self, ip, ctry):
        if len(self.geoDb) == 0:
            return None
        for i in ip:
            if i < 0 or i > 255:
                return None
        res = self.findCtry(ip, 0, len(self.geoDb)-1)
        if res == None:
            return False
        if res.lower() == ctry.lower():
            if self.debug:
                print "country found:", res.lower()
            return True
        return False

    def findCtry(self, ip, start, end):
        if self.debug:
            print "start:", start, "and end:", end
        if start>end:
            return None
        if start == end:
            mid = self.geoDb[start]
            lower, upper = mid[0].split('.'), mid[1].split('.')
            ipIntVal = self.dotQuadToInt(ip)
            if ipIntVal >= self.dotQuadToInt(lower) and ipIntVal <= self.dotQuadToInt(upper):
                return mid[2]
            return None
        mid = self.geoDb[(start+end)/2]
        lower, upper = mid[0].split('.'), mid[1].split('.')
        ipIntVal = self.dotQuadToInt(ip)
        if ipIntVal < self.dotQuadToInt(lower):
            return self.findCtry(ip, start, (start+end)/2-1)
        elif ipIntVal > self.dotQuadToInt(upper):
            if self.debug:
                print "ipIntVal is greater than upper:", start, "and", end
            return self.findCtry(ip, (start+end)/2+1, end)
        return mid[2]


    def proIpPortMatching(self, pkt_info):
        if self.debug:
            print "entered proTpPortMatching"
            print pkt_info
        for rule in reversed(self.rules):
            rule = [r.lower() for r in rule]
            if self.debug:
                print "rule is", rule
            if self.ipv4ProHash[pkt_info['ip_protocal']] == rule[1]:
                if self.debug:
                    print "pkt's ipv4 protocal:", rule[1]
                if len(rule[2]) == 2:
                    # country code
                    if self.debug:
                        print "isInCountry: \n", self.isInCountry(pkt_info['external_ip'], rule[2])
                    if self.isInCountry(pkt_info['external_ip'], rule[2]):
                        if rule[3] == 'any':
                            return rule[0]
                        elif '-' in rule[3]:
                            lower, upper = rule[3].split('-')
                            lower, upper = int(lower), int(upper)
                            if pkt_info['external_port'] <= upper and pkt_info['external_port'] >= lower:
                                return rule[0]
                        else:
                            if pkt_info['external_port'] == int(rule[3]):
                                return rule[0]
                    
                elif rule[2]  == 'any':
                    if self.debug:
                        print "rule says that external ip can be anything"
                    if rule[3] == 'any':
                        return rule[0]
                    elif '-' in rule[3]:
                        lower, upper = rule[3].split('-')
                        lower, upper = int(lower), int(upper)
                        if pkt_info['external_port'] <= upper and pkt_info['external_port'] >= lower:
                            return rule[0]
                    else:
                        if self.debug:
                            print "rule says that external port should be", rule[3]
                        if pkt_info['external_port'] == int(rule[3]):
                            return rule[0]
                else:
                    quad = rule[2].split('.')
                    if '/' in quad[3]:
                        # an IP prefix
                        last_quad, offset = quad[3].split('/')
                        last_quad = int(last_quad)
                        offset = int(offset)
                        base_quad = quad[:3]
                        base_quad.append(last_quad)
                        if self.dotQuadToInt(base_quad) >> (32 - offset) == self.dotQuadToInt(pkt_info['external_ip']) >> (32 - offset):
                            if self.debug:
                                print "range matched:", quad
                            if rule[3] == 'any':
                                return rule[0]
                            elif '-' in rule[3]:
                                lower, upper = rule[3].split('-')
                                lower, upper = int(lower), int(upper)
                                if pkt_info['external_port'] <= upper and pkt_info['external_port'] >= lower:
                                    return rule[0]
                            else:
                                if pkt_info['external_port'] == int(rule[3]):
                                    return rule[0]
                    else:
                        # a single IP address
                        if self.dotQuadToInt(quad) == self.dotQuadToInt(pkt_info['external_ip']):
                            if self.debug:
                                print "single ip matched:", quad
                            if rule[3] == 'any':
                                return rule[0]
                            elif '-' in rule[3]:
                                lower, upper = rule[3].split('-')
                                lower, upper = int(lower), int(upper)
                                if pkt_info['external_port'] <= upper and pkt_info['external_port'] >= lower:
                                    return rule[0]
                            else:
                                if pkt_info['external_port'] == int(rule[3]):
                                    return rule[0]

        return "pass"
                                    
    def dnsMatching(self, addr, pkt_info):        # make sure the dnsName are all in lower case
        addr_lst = addr.split(".")
        for j in range(1,len(self.rules)+1):
            rule = self.rules[-j]
            if rule[1]=="dns":
                dnsRule = rule
                dnsAddr_lst = dnsRule[2].split(".")
                matched = True
                if len(dnsAddr_lst)>len(addr_lst):
                    continue
                else:
                    for i in range(1,len(dnsAddr_lst)+1):
                        if dnsAddr_lst[-i]=="*":
                            break
                        elif dnsAddr_lst[-i]!=addr_lst[-i]:
                            matched = False
                            break
                    if matched:
                        return dnsRule[0]
            else:
                if rule[1]=="udp":
                    if len(rule[2]) == 2:
                        # country code
                        if self.debug:
                            print "isInCountry:", self.isInCountry(pkt_info['external_ip'], rule[2])
                        if self.isInCountry(pkt_info['external_ip'], rule[2]):
                            if rule[3] == 'any':
                                return rule[0]
                            elif '-' in rule[3]:
                                lower, upper = rule[3].split('-')
                                lower, upper = int(lower), int(upper)
                                if pkt_info['external_port'] <= upper and pkt_info['external_port'] >= lower:
                                    return rule[0]
                            else:
                                if pkt_info['external_port'] == int(rule[3]):
                                    return rule[0]

                    elif rule[2]  == 'any':
                        if self.debug:
                            print "rule says that external ip can be anything"
                        if rule[3] == 'any':
                            return rule[0]
                        elif '-' in rule[3]:
                            lower, upper = rule[3].split('-')
                            lower, upper = int(lower), int(upper)
                            if pkt_info['external_port'] <= upper and pkt_info['external_port'] >= lower:
                                return rule[0]
                        else:
                            if self.debug:
                                print "rule says that external port should be", rule[3]
                            if pkt_info['external_port'] == int(rule[3]):
                                return rule[0]
                    else:
                        quad = rule[2].split('.')
                        if '/' in quad[3]:
                            # an IP prefix
                            last_quad, offset = quad[3].split('/')
                            last_quad = int(last_quad)
                            offset = int(offset)
                            base_quad = quad[:3]
                            base_quad.append(last_quad)
                            if self.dotQuadToInt(base_quad) >> (32 - offset) == self.dotQuadToInt(pkt_info['external_ip']) >> (32 - offset):
                                if self.debug:
                                    print "range matched:", quad
                                if rule[3] == 'any':
                                    return rule[0]
                                elif '-' in rule[3]:
                                    lower, upper = rule[3].split('-')
                                    lower, upper = int(lower), int(upper)
                                    if pkt_info['external_port'] <= upper and pkt_info['external_port'] >= lower:
                                        return rule[0]
                                else:
                                    if pkt_info['external_port'] == int(rule[3]):
                                        return rule[0]
                        else:
                            # a single IP address
                            if self.dotQuadToInt(quad) == self.dotQuadToInt(pkt_info['external_ip']):
                                if self.debug:
                                    print "single ip matched:", quad
                                if rule[3] == 'any':
                                    return rule[0]
                                elif '-' in rule[3]:
                                    lower, upper = rule[3].split('-')
                                    lower, upper = int(lower), int(upper)
                                    if pkt_info['external_port'] <= upper and pkt_info['external_port'] >= lower:
                                        return rule[0]
                                else:
                                    if pkt_info['external_port'] == int(rule[3]):
                                        return rule[0]

        return "no-match"    # self-defined third return value besides "pass" and "drop"

    def checkDnsQuery(self, pkt):
        udpLength = struct.unpack('!H', pkt[4:6])[0]
        dnsHeader = pkt[8:20]
        QDCOUNT = struct.unpack("!H", dnsHeader[4:6])[0]
        if QDCOUNT!=1:
            return [False, ""]
        j = 20
        dnsName = ""
        if self.debug:
            print "PKT: ", pkt, " length: ", len(pkt)
        while j<udpLength:
            hex = struct.unpack("!B",pkt[j])[0]
            if hex==0x00:
                j+=1
                break
            else:
                if (hex>=65 and hex<=90) or (hex>=97 and hex<=122) or (hex>=48 and hex<=57) or hex==45:  # only alphabetic letters, digits and hyphen are permitted as dns name
                    dnsName = dnsName+chr(hex)
                elif dnsName!="": # beginning of parsing, first hex number not letters/hyphens is just number of letters behind
                    dnsName = dnsName+"."       # adding dot
                j+=1
        dnsName=dnsName.lower()
        QTYPE = struct.unpack("!H", pkt[j:j+2])[0]
        QCLASS = struct.unpack("!H", pkt[j+2:j+4])[0]
        if (QTYPE==1 or QTYPE==28) and QCLASS==1 and QDCOUNT==1:
            return [True, dnsName]
        return [False, dnsName]


