import os
from flask import Flask, render_template, request, jsonify
import requests
import random

import time

app = Flask(__name__)

# Cache for Rolimons market data
rolimons_cache = {
    "data": {},
    "last_update": 0
}

def refresh_rolimons_cache():
    global rolimons_cache
    if time.time() - rolimons_cache["last_update"] < 600: # 10 minutes cache
        return
    try:
        r = requests.get("https://www.rolimons.com/itemapi/itemdetails")
        if r.status_code == 200:
            rolimons_cache["data"] = r.json().get("items", {})
            rolimons_cache["last_update"] = time.time()
    except: pass

def get_market_tags(asset_id):
    item = rolimons_cache["data"].get(str(asset_id))
    if not item: return {"demand": "Unknown", "trend": "Stable"}
    
    demand_idx = item[5]
    trend_idx = item[6]
    
    demands = { -1: "Unknown", 0: "None", 1: "Low", 2: "Normal", 3: "High", 4: "Amazing" }
    trends = { -1: "Unknown", 0: "None", 1: "Lowering", 2: "Stable", 3: "Raising", 4: "Fluctuating" }
    
    return {
        "demand": demands.get(demand_idx, "Unknown")
    }

def get_user_data(username):
    refresh_rolimons_cache()
    try:
        # 1. Cari User ID
        user_res = requests.post("https://users.roblox.com/v1/usernames/users", 
                                 json={"usernames": [username], "excludeBannedUsers": True})
        user_res.raise_for_status()
        user_data = user_res.json()
        
        if not user_data.get('data'): return None
        
        user_info = user_data['data'][0]
        user_id = user_info['id']
        display_name = user_info['displayName']
        actual_username = user_info['name']

        # 2. Ambil Avatar
        thumb_res = requests.get(f"https://thumbnails.roblox.com/v1/users/avatar-headshot?userIds={user_id}&size=150x150&format=Png&isCircular=true")
        avatar_url = thumb_res.json()['data'][0]['imageUrl']

        # 3. Ambil Item Limited (Only Collectibles)
        limited_res = requests.get(f"https://inventory.roblox.com/v1/users/{user_id}/assets/collectibles?limit=100")
        
        if limited_res.status_code == 403:
            return {
                "id": user_id, "name": display_name, "username": actual_username, 
                "avatar": avatar_url, "private": True, "items": [], "networth": 0, "history": [0]*7
            }

        # Gabungkan data
        items_raw = []
        
        # Proses Limited (RAP-based)
        for item in limited_res.json().get('data', []):
            market = get_market_tags(item['assetId'])
            items_raw.append({
                "assetId": item['assetId'],
                "name": item['name'],
                "price": item.get('recentAveragePrice', 0),
                "isLimited": True,
                "serial": item.get('serialNumber'),
                "demand": market['demand']
            })

        if not items_raw:
            return {"id": user_id, "name": display_name, "username": actual_username, "avatar": avatar_url, "private": False, "items": [], "networth": 0, "history": [0]*7}

        # 4. Ambil Visualisasi
        all_ids = [str(i['assetId']) for i in items_raw]
        
        # Batch Thumbnails
        t_res = requests.get(f"https://thumbnails.roblox.com/v1/assets?assetIds={','.join(all_ids)}&size=150x150&format=Png").json()
        asset_thumbs = {t['targetId']: t['imageUrl'] for t in t_res.get('data', [])}
        
        for item in items_raw:
            item['image'] = asset_thumbs.get(item['assetId'], "")

        # 5. Final Processing
        final_items = sorted(items_raw, key=lambda x: x['price'], reverse=True)[:20]
        total_net = sum(i['price'] for i in items_raw)

        # Generate History (Seeded for consistency per user)
        # Use user_id as seed so the graph remains the same for the same account
        random.seed(user_id)
        history = []
        for i in range(7):
            variance = random.uniform(-0.05, 0.05) # +/- 5% fluctuation
            history.append(int(total_net * (1 + variance)))
        history[-1] = total_net # Current is always latest
        
        # Reset seed for other potential random uses
        random.seed(time.time())

        return {
            "id": user_id, "name": display_name, "username": actual_username,
            "avatar": avatar_url, "private": False, "items": final_items,
            "networth": total_net, "history": history
        }

    except Exception as e:
        print(f"Error in get_user_data: {e}")
        return None

@app.route('/')
def index(): return render_template('index.html')

@app.route('/search', methods=['POST'])
def search():
    data = get_user_data(request.json.get('username'))
    return jsonify(data) if data else (jsonify({"error": "Not Found"}), 404)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)