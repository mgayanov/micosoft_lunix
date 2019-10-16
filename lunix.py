import hashlib

def get_email_hash(email):
	
	h = [0]*32

	for sym in email:
		
		sha256 = hashlib.sha256(sym.encode()).digest()
		for i in range(32):
			s = h[i] + sha256[i]

			if s <= 0xEC:
				h[i] = s
			else:
				h[i] = s % 0xEC
	return h

def keygen(email):

	email_hash = get_email_hash(email)

	print(print(bytearray(email_hash).hex()))


	pairs = [(0x00, 0x1c), (0x1f, 0x03), (0x01, 0x1d), (0x1e, 0x02),
		 (0x04, 0x18), (0x1b, 0x07), (0x05, 0x19), (0x1a, 0x06),
		 (0x08, 0x14), (0x17, 0x0b), (0x09, 0x15), (0x16, 0x0a),
		 (0x0c, 0x10), (0x13, 0x0f), (0x0d, 0x11), (0x12, 0x0e)]

	key = []

	for pair in pairs:
		i = pair[0]
		j = pair[1]
		key.append((email_hash[i] * email_hash[j])%9)

	return [''.join(map(str, key[i:i+4])) for i in range(0, 16, 4)]
