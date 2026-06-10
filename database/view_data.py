"""
查看数据库中的用户、上传历史与车辆数据 — 命令行查看器

直接运行打印全部内容；也可通过参数单独输出某一部分、限定条数、或只看某个用户。

用法示例:
    python view_data.py                      # 输出全部（各区块默认限 10 条）
    python view_data.py --users              # 只看用户列表
    python view_data.py --uploads --active   # 只看上传历史 + 各用户当前生效批次
    python view_data.py --vehicles --limit 20            # 当前车辆数据，每用户最多 20 条
    python view_data.py --history --upload 3             # 第 3 次上传归档的明细
    python view_data.py --user 张三 --vehicles --stats   # 只看某个用户
    python view_data.py --all --limit 0                  # 全部区块、不限条数(0=不限)

区块开关（不传则默认输出全部区块）:
    --users 用户列表  --uploads 上传历史  --active 当前生效批次
    --stats 各用户统计  --vehicles 当前车辆数据  --history 上传归档明细
"""
import sqlite3
import os
import argparse
import sys

DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'app.db')

SECTION_FLAGS = ['users', 'uploads', 'active', 'stats', 'vehicles', 'history']


def parse_args():
    p = argparse.ArgumentParser(
        description='汽车数据可视化平台 — 数据库查看器',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    # 区块开关
    p.add_argument('--users', action='store_true', help='输出用户列表')
    p.add_argument('--uploads', action='store_true', help='输出上传历史记录')
    p.add_argument('--active', action='store_true', help='输出各用户当前生效的上传批次')
    p.add_argument('--stats', action='store_true', help='输出各用户数据统计')
    p.add_argument('--vehicles', action='store_true', help='输出当前车辆数据明细')
    p.add_argument('--history', action='store_true', help='输出上传归档明细（按 upload 区分）')
    p.add_argument('--all', action='store_true', help='输出全部区块（等价于不传任何区块开关）')
    # 过滤 / 限制
    p.add_argument('--user', metavar='ID或用户名', help='只看指定用户（可填用户 id 或用户名）')
    p.add_argument('--upload', type=int, metavar='ID', help='只看指定 upload_id（用于 --history）')
    p.add_argument('--limit', type=int, default=10, metavar='N',
                   help='行明细区块每组最多输出的条数，0 表示不限（默认 10）')
    return p.parse_args()


def resolve_user(conn, user_arg):
    """把 --user 的值（id 或用户名）解析为一行用户记录；找不到则退出。"""
    if user_arg is None:
        return None
    row = None
    if str(user_arg).isdigit():
        # 纯数字优先按 id 查；查不到再按用户名（兼容全数字用户名）
        row = conn.execute('SELECT * FROM users WHERE id = ?', (int(user_arg),)).fetchone()
    if row is None:
        row = conn.execute('SELECT * FROM users WHERE username = ?', (user_arg,)).fetchone()
    if row is None:
        print(f'  ✗ 未找到用户: {user_arg}')
        sys.exit(1)
    return row


def has_column(conn, table, column):
    return column in [r['name'] for r in conn.execute(f'PRAGMA table_info({table})')]


def lim(sql, limit):
    """在 SQL 末尾按需追加 LIMIT（limit<=0 表示不限）。"""
    return sql if (limit is None or limit <= 0) else f'{sql} LIMIT {int(limit)}'


def section(title):
    print(f'\n【{title}】')


# ── 各区块 ──

def show_users(conn, user_row):
    section('用户列表')
    print(f'  {"ID":<5} {"用户名":<16} {"注册时间":<20}')
    print(f'  {"-"*5} {"-"*16} {"-"*20}')
    where, params = ('WHERE id = ?', (user_row['id'],)) if user_row else ('', ())
    for r in conn.execute(f'SELECT id, username, created_at FROM users {where} ORDER BY id', params):
        print(f'  {r["id"]:<5} {r["username"]:<16} {r["created_at"]:<20}')


def show_active(conn, user_row):
    section('各用户当前生效的上传批次 (active)')
    if not has_column(conn, 'users', 'active_upload_id'):
        print('  (该数据库尚无 active_upload_id 列，请先用新版后端启动一次)')
        return
    print(f'  {"用户":<16} {"active_upload":<14} {"文件名":<24} {"记录数":<8}')
    print(f'  {"-"*16} {"-"*14} {"-"*24} {"-"*8}')
    where, params = ('WHERE u.id = ?', (user_row['id'],)) if user_row else ('', ())
    for r in conn.execute(f'''
        SELECT u.username, u.active_upload_id, up.filename, up.record_count
        FROM users u
        LEFT JOIN uploads up ON up.id = u.active_upload_id
        {where} ORDER BY u.id
    ''', params):
        aid = r['active_upload_id'] if r['active_upload_id'] is not None else '-'
        print(f'  {r["username"]:<16} {str(aid):<14} {(r["filename"] or "-"):<24} {str(r["record_count"] if r["record_count"] is not None else "-"):<8}')


def show_uploads(conn, user_row, limit):
    section('上传历史记录')
    archived = _table_exists(conn, 'upload_vehicles')
    print(f'  {"ID":<5} {"用户":<14} {"文件名":<24} {"记录数":<7} {"归档":<6} {"上传时间":<20}')
    print(f'  {"-"*5} {"-"*14} {"-"*24} {"-"*7} {"-"*6} {"-"*20}')
    where, params = ('WHERE up.user_id = ?', (user_row['id'],)) if user_row else ('', ())
    sql = f'''
        SELECT up.id, u.username, up.filename, up.record_count, up.created_at,
               (SELECT COUNT(*) FROM upload_vehicles uv WHERE uv.upload_id = up.id) AS archived_count
        FROM uploads up JOIN users u ON u.id = up.user_id
        {where}
        ORDER BY up.created_at DESC, up.id DESC
    ''' if archived else f'''
        SELECT up.id, u.username, up.filename, up.record_count, up.created_at,
               0 AS archived_count
        FROM uploads up JOIN users u ON u.id = up.user_id
        {where}
        ORDER BY up.created_at DESC, up.id DESC
    '''
    for r in conn.execute(lim(sql, limit), params):
        print(f'  {r["id"]:<5} {r["username"]:<14} {r["filename"]:<24} {r["record_count"]:<7} {r["archived_count"]:<6} {r["created_at"]:<20}')


def show_stats(conn, user_row):
    section('各用户数据统计')
    print(f'  {"用户":<16} {"车辆数":<8} {"品牌数":<8} {"上传次数":<8}')
    print(f'  {"-"*16} {"-"*8} {"-"*8} {"-"*8}')
    where, params = ('WHERE u.id = ?', (user_row['id'],)) if user_row else ('', ())
    for r in conn.execute(f'''
        SELECT u.username,
               COUNT(DISTINCT v.id) as v_count,
               COUNT(DISTINCT v.brand) as b_count,
               COUNT(DISTINCT up.id) as u_count
        FROM users u
        LEFT JOIN vehicles v ON v.user_id = u.id
        LEFT JOIN uploads up ON up.user_id = u.id
        {where}
        GROUP BY u.id
        ORDER BY u.id
    ''', params):
        print(f'  {r["username"]:<16} {r["v_count"]:<8} {r["b_count"]:<8} {r["u_count"]:<8}')


def _print_vehicle_rows(rows):
    print(f'  {"品牌":<10} {"车型":<14} {"销量":<8} {"价格(万)":<10} {"能源":<6}')
    for v in rows:
        print(f'  {v["brand"]:<10} {v["model"]:<14} {v["sales_volume"]:<8} {v["sales_price"]:<10} {v["energy_type"]:<6}')


def show_vehicles(conn, user_row, limit):
    suffix = '全部' if (limit is None or limit <= 0) else f'前{limit}条'
    section(f'当前车辆数据明细（各用户{suffix}）')
    users = [user_row] if user_row else conn.execute('SELECT id, username FROM users ORDER BY id').fetchall()
    for user in users:
        rows = conn.execute(
            lim('SELECT brand, model, sales_volume, sales_price, energy_type '
                'FROM vehicles WHERE user_id = ? ORDER BY sales_volume DESC', limit),
            (user['id'],)
        ).fetchall()
        if rows:
            print(f'\n  >>> {user["username"]} 的当前数据 ({len(rows)} 条显示):')
            _print_vehicle_rows(rows)
        else:
            print(f'\n  >>> {user["username"]}: 暂无当前数据')


def _table_exists(conn, table):
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone() is not None


def show_history(conn, user_row, limit, upload_id):
    section('上传归档明细 (upload_vehicles)')
    if not _table_exists(conn, 'upload_vehicles'):
        print('  (该数据库尚无 upload_vehicles 表，请先用新版后端启动一次)')
        return
    where = []
    params = []
    if user_row:
        where.append('up.user_id = ?'); params.append(user_row['id'])
    if upload_id is not None:
        where.append('up.id = ?'); params.append(upload_id)
    wsql = ('WHERE ' + ' AND '.join(where)) if where else ''
    uploads = conn.execute(f'''
        SELECT up.id, u.username, up.filename, up.created_at,
               (SELECT COUNT(*) FROM upload_vehicles uv WHERE uv.upload_id = up.id) AS cnt
        FROM uploads up JOIN users u ON u.id = up.user_id
        {wsql}
        ORDER BY up.created_at DESC, up.id DESC
    ''', params).fetchall()
    if not uploads:
        print('  (没有匹配的上传记录)')
        return
    for up in uploads:
        suffix = '全部' if (limit is None or limit <= 0) else f'前{limit}条'
        print(f'\n  >>> upload#{up["id"]} · {up["username"]} · {up["filename"]} · {up["created_at"]} · 归档 {up["cnt"]} 条（显示{suffix}）')
        rows = conn.execute(
            lim('SELECT brand, model, sales_volume, sales_price, energy_type '
                'FROM upload_vehicles WHERE upload_id = ? ORDER BY sales_volume DESC', limit),
            (up['id'],)
        ).fetchall()
        if rows:
            _print_vehicle_rows(rows)
        else:
            print('  (无归档明细)')


def main():
    if not os.path.exists(DB):
        print('数据库文件尚不存在，请先启动后端并注册用户。')
        return

    args = parse_args()
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row

    # 未指定任何区块 → 输出全部
    selected = {f: getattr(args, f) for f in SECTION_FLAGS}
    if args.all or not any(selected.values()):
        selected = {f: True for f in SECTION_FLAGS}

    user_row = resolve_user(conn, args.user)

    print('=' * 60)
    print('  汽车数据可视化平台 — 数据库管理视图')
    if user_row:
        print(f'  过滤用户: {user_row["username"]} (id={user_row["id"]})')
    print('=' * 60)

    if selected['users']:    show_users(conn, user_row)
    if selected['active']:   show_active(conn, user_row)
    if selected['uploads']:  show_uploads(conn, user_row, args.limit)
    if selected['stats']:    show_stats(conn, user_row)
    if selected['vehicles']: show_vehicles(conn, user_row, args.limit)
    if selected['history']:  show_history(conn, user_row, args.limit, args.upload)

    conn.close()
    print('\n' + '=' * 60)


if __name__ == '__main__':
    main()
