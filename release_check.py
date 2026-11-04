"""Fail-closed release readiness check for a running Seed Reflections deployment."""
import argparse, json, sys, urllib.error, urllib.request

def main(argv=None):
    parser=argparse.ArgumentParser(); parser.add_argument("--origin",required=True); args=parser.parse_args(argv)
    url=args.origin.rstrip("/")+"/api/v2/readiness"
    try:
        with urllib.request.urlopen(url,timeout=15) as response: result=json.loads(response.read())
    except urllib.error.HTTPError as exc:
        try: result=json.loads(exc.read())
        except Exception: result={"ready":False,"checks":[],"error":str(exc)}
    except Exception as exc: result={"ready":False,"checks":[],"error":str(exc)}
    print(json.dumps(result,indent=2)); return 0 if result.get("ready") else 1

if __name__=="__main__": raise SystemExit(main())
