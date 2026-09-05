/**
 * Checks if the given IP address is a local/private IP address.
 * Only standard loopback and RFC 1918 private IP subnets are identified as local.
 * Korean public ISP IPs are NOT treated as local — they are public IPs and
 * PII cleanup must apply per Korean data protection law.
 */
export function isLocalIp(ip: string | null | undefined): boolean {
  if (!ip) return false;

  const trimmedIp = ip.trim();

  // 1. Loopback addresses (IPv4 & IPv6)
  if (
    trimmedIp === '127.0.0.1' ||
    trimmedIp === '::1' ||
    trimmedIp === 'localhost' ||
    trimmedIp.startsWith('::ffff:127.0.0.1')
  ) {
    return true;
  }

  // 2. Private IP networks (RFC 1918)
  if (
    trimmedIp.startsWith('10.') ||
    trimmedIp.startsWith('192.168.') ||
    /^172\.(1[6-9]|2[0-9]|3[0-1])\./.test(trimmedIp)
  ) {
    return true;
  }

  // 3. Link-local addresses (169.254.0.0/16)
  if (trimmedIp.startsWith('169.254.')) {
    return true;
  }

  return false;
}
