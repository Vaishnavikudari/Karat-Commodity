import os
import sys
import json
import urllib.request
import urllib.error

FIGMA_TOKEN = os.environ.get("FIGMA_TOKEN", "")

def figma_get(endpoint):
    url = f"https://api.figma.com/v1/{endpoint.lstrip('/')}"
    req = urllib.request.Request(url, headers={"X-Figma-Token": FIGMA_TOKEN})
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"HTTPError {e.code}: {e.read().decode('utf-8')}", file=sys.stderr)
        raise

def get_file(file_key, depth=2):
    return figma_get(f"files/{file_key}?depth={depth}")

def get_file_nodes(file_key, ids):
    return figma_get(f"files/{file_key}/nodes?ids={','.join(ids)}")

def get_image(file_key, ids, format="svg", scale=1):
    return figma_get(f"images/{file_key}?ids={','.join(ids)}&format={format}&scale={scale}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python figma_client.py <file_key_or_url> [depth]")
        sys.exit(1)

    target = sys.argv[1]
    # Extract file key from URL if URL was passed
    if "figma.com/" in target:
        parts = target.split("figma.com/")[1].split("/")
        # format: file/KEY/title or design/KEY/title
        if parts[0] in ["file", "design"] and len(parts) > 1:
            file_key = parts[1]
        else:
            file_key = parts[0]
    else:
        file_key = target

    depth = int(sys.argv[2]) if len(sys.argv) > 2 else 2
    data = get_file(file_key, depth=depth)
    print(f"File Name: {data.get('name')}")
    print(f"Last Modified: {data.get('lastModified')}")
    document = data.get("document", {})
    for canvas in document.get("children", []):
        print(f"Page: {canvas.get('name')} (id: {canvas.get('id')})")
        for frame in canvas.get("children", []):
            print(f"  - Frame: {frame.get('name')} (id: {frame.get('id')}, type: {frame.get('type')})")
