"""查看数据库中的用户和上传信息 — 直接运行即可"""
import sqlite3
import os

DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'app.db')

if not os.path.exists(DB):
    print('数据库文件尚不存在，请先启动后端并注册用户。')
    exit()

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row

print('=' * 55)
print('  汽车数据可视化平台 — 数据库管理视图')
print('=' * 55)

print('\n【用户列表】')
print(f'  {"ID":<5} {"用户名":<16} {"注册时间":<20}')
print(f'  {"-"*5} {"-"*16} {"-"*20}')
for r in conn.execute('SELECT id, username, created_at FROM users ORDER BY id'):
    print(f'  {r["id"]:<5} {r["username"]:<16} {r["created_at"]:<20}')

print('\n【上传记录】')
print(f'  {"用户":<16} {"文件名":<24} {"记录数":<8} {"上传时间":<20}')
print(f'  {"-"*16} {"-"*24} {"-"*8} {"-"*20}')
for r in conn.execute('''
    SELECT u.username, up.filename, up.record_count, up.created_at
    FROM uploads up JOIN users u ON u.id = up.user_id
    ORDER BY up.created_at DESC
'''):
    print(f'  {r["username"]:<16} {r["filename"]:<24} {r["record_count"]:<8} {r["created_at"]:<20}')

print('\n【各用户数据统计】')
print(f'  {"用户":<16} {"车辆数":<8} {"品牌数":<8} {"上传次数":<8}')
print(f'  {"-"*16} {"-"*8} {"-"*8} {"-"*8}')
for r in conn.execute('''
    SELECT u.username,
           COUNT(DISTINCT v.id) as v_count,
           COUNT(DISTINCT v.brand) as b_count,
           COUNT(DISTINCT up.id) as u_count
    FROM users u
    LEFT JOIN vehicles v ON v.user_id = u.id
    LEFT JOIN uploads up ON up.user_id = u.id
    GROUP BY u.id
    ORDER BY u.id
'''):
    print(f'  {r["username"]:<16} {r["v_count"]:<8} {r["b_count"]:<8} {r["u_count"]:<8}')

print('\n【原始车辆数据预览（各用户前5条）】')
for user in conn.execute('SELECT id, username FROM users ORDER BY id'):
    vehicles = conn.execute(
        'SELECT brand, model, sales_volume, sales_price, energy_type FROM vehicles WHERE user_id = ? LIMIT 5',
        (user['id'],)
    ).fetchall()
    if vehicles:
        print(f'\n  >>> {user["username"]} 的数据:')
        print(f'  {"品牌":<10} {"车型":<14} {"销量":<8} {"价格(万)":<10} {"能源":<6}')
        for v in vehicles:
            print(f'  {v["brand"]:<10} {v["model"]:<14} {v["sales_volume"]:<8} {v["sales_price"]:<10} {v["energy_type"]:<6}')
    else:
        print(f'\n  >>> {user["username"]}: 暂无数据')

conn.close()
print('\n' + '=' * 55)
