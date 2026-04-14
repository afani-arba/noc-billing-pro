"""
Ping Service — ICMP & TCP connectivity checks.
Digunakan oleh polling untuk mengukur latency/reachability ke device itu sendiri.
"""
import asyncio
import logging
import re
import time as _time

logger = logging.getLogger(__name__)


async def ping_host(host: str, count: int = 4, timeout: int = 5) -> dict:
    """
    Real ICMP ping ke host (IP device MikroTik).
    Mengembalikan latency, packet loss, dan jitter hasil ping ke device.

    FIX BUG #5: Sebelumnya selalu ping ke 8.8.8.8/1.1.1.1 (internet),
    bukan ke device. Sekarang ping langsung ke host yang diberikan.
    """
    if not host:
        return {"reachable": False, "min": 0, "avg": 0, "max": 0, "jitter": 0, "loss": 100}

    return await _icmp_ping(host, count=count, timeout=timeout)


async def _icmp_ping(target: str, count: int = 4, timeout: int = 5) -> dict:
    """
    Real ICMP ping menggunakan system ping command.
    Berjalan di Linux (server) dengan binary ping standar.

    FIX BUG #6: asyncio.wait_for sekarang membungkus proc.communicate(),
    bukan hanya pembuatan subprocess. Ini mencegah hang tak terbatas.
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            "ping", "-c", str(count), "-W", str(timeout), "-q", target,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        # FIX BUG #6: wrap communicate() dengan wait_for, bukan create_subprocess_exec
        try:
            stdout, _ = await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout * count + 5
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            logger.debug(f"ICMP ping ke {target} timeout")
            return {"reachable": False, "min": 0, "avg": 0, "max": 0, "jitter": 0, "loss": 100, "target": target}

        output = stdout.decode("utf-8", errors="ignore")

        # Parse packet loss
        loss = 100
        loss_match = re.search(r"(\d+)%\s+packet\s+loss", output)
        if loss_match:
            loss = int(loss_match.group(1))

        # Parse rtt min/avg/max/mdev
        rtt_match = re.search(
            r"rtt\s+min/avg/max/mdev\s*=\s*([\d.]+)/([\d.]+)/([\d.]+)/([\d.]+)",
            output
        )
        if rtt_match:
            return {
                "reachable": loss < 100,
                "min":    round(float(rtt_match.group(1)), 2),
                "avg":    round(float(rtt_match.group(2)), 2),
                "max":    round(float(rtt_match.group(3)), 2),
                "jitter": round(float(rtt_match.group(4)), 2),
                "loss":   loss,
                "target": target,
            }

        return {"reachable": False, "min": 0, "avg": 0, "max": 0, "jitter": 0, "loss": 100, "target": target}

    except Exception as e:
        logger.debug(f"ICMP ping ke {target} gagal: {e}")
        return {"reachable": False, "min": 0, "avg": 0, "max": 0, "jitter": 0, "loss": 100, "target": target}


async def internet_ping(count: int = 2, timeout: int = 3) -> dict:
    """
    Ping ke internet (8.8.8.8 dan 1.1.1.1) untuk memeriksa konektivitas server.
    Terpisah dari ping_host agar tidak bertukar fungsi.
    Mengembalikan hasil terbaik (latency terendah) dari kedua target.
    """
    results = await asyncio.gather(
        _icmp_ping("8.8.8.8", count=count, timeout=timeout),
        _icmp_ping("1.1.1.1", count=count, timeout=timeout),
        return_exceptions=True
    )

    valid = [r for r in results if isinstance(r, dict) and r.get("reachable")]

    if not valid:
        return {"reachable": False, "min": 0, "avg": 0, "max": 0, "jitter": 0, "loss": 100}

    # Kembalikan jalur internet terbaik (avg ping terendah)
    best = min(valid, key=lambda r: r.get("avg", 9999))
    return best


async def tcp_ping(host: str, ports: list, count: int = 3, timeout: int = 2) -> dict:
    """
    TCP ping fallback — cek reachability via TCP handshake.
    Berguna jika ICMP diblok tapi TCP port terbuka.
    """
    latencies = []

    for _ in range(count):
        for port in ports:
            try:
                start = _time.monotonic()
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(host, port),
                    timeout=timeout
                )
                latency = (_time.monotonic() - start) * 1000
                latencies.append(latency)
                writer.close()
                try:
                    await writer.wait_closed()
                except Exception:
                    pass
                break
            except Exception:
                continue

    if latencies:
        avg = sum(latencies) / len(latencies)
        min_lat = min(latencies)
        max_lat = max(latencies)
        jitter = sum(abs(l - avg) for l in latencies) / len(latencies) if len(latencies) > 1 else 0
        return {
            "reachable": True,
            "min":    round(min_lat, 2),
            "avg":    round(avg, 2),
            "max":    round(max_lat, 2),
            "jitter": round(jitter, 2),
            "loss":   round((count - len(latencies)) / count * 100),
        }

    return {"reachable": False, "min": 0, "avg": 0, "max": 0, "jitter": 0, "loss": 100}
