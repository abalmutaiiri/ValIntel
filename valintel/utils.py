"""Small shared helpers."""

def pd_from_glz(glz):
    host = glz.replace("https://", "").split(".")
    shard = host[1] if len(host) > 2 else "na"
    return f"https://pd.{shard}.a.pvp.net"
