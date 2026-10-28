import os
import re
import json

def parse_html_records(filepath):
    if not os.path.exists(filepath):
        return None
    with open(filepath, 'r', encoding='utf-8') as f:
        html = f.read()
    matches = re.findall(r'(\[\{"d":"\d{4}-\d{2}-\d{2}".*?\}\])', html)
    if matches:
        largest = max(matches, key=len)
        return json.loads(largest)
    return None

def compute_cell_stat(records, market_type='bull', fg='Neutral', q='Q1', is_short_box=True, side='long'):
    if not records:
        return {'days': 0, 'win': 50.0, 'ret': 0.0}
    if market_type == 'bull':
        active = [r for r in records if r.get('mt') == 1]
    elif market_type == 'non_bull':
        active = [r for r in records if r.get('mt') == 0]
    else:
        active = records
        
    liqrs = sorted([r['li'] for r in active])
    siqrs = sorted([r['si'] for r in active])
    
    def get_med(s):
        if not s: return 15.0
        mid = len(s) // 2
        return s[mid] if len(s) % 2 != 0 else (s[mid-1] + s[mid]) / 2.0
        
    dyn_l_med = get_med(liqrs)
    dyn_s_med = get_med(siqrs)
    
    if side == 'long':
        match = [r for r in active if r.get('fg') == fg and r.get('lq') == q]
        box_match = [r for r in match if r['li'] <= dyn_l_med] if is_short_box else [r for r in match if r['li'] > dyn_l_med]
        win_col = 'lp'
        ret_col = 'la'
    else:
        match = [r for r in active if r.get('fg') == fg and r.get('sq') == q]
        box_match = [r for r in match if r['si'] <= dyn_s_med] if is_short_box else [r for r in match if r['si'] > dyn_s_med]
        win_col = 'sp'
        ret_col = 'sa'
        
    days = len(box_match)
    if days == 0:
        if len(match) > 0:
            win = (sum(r[win_col] for r in match) / len(match)) * 100.0
            ret = sum(r[ret_col] for r in match) / len(match)
            return {'days': len(match), 'win': win, 'ret': ret}
        return {'days': 0, 'win': 50.0, 'ret': 0.0}
        
    win = (sum(r[win_col] for r in box_match) / days) * 100.0
    ret = sum(r[ret_col] for r in box_match) / days
    return {'days': days, 'win': win, 'ret': ret}

class DynamicCompassEngine:
    def __init__(self, base_dir=r'c:\Users\araya\anaconda_projects\demo_jlab', master_csv_path=None):
        self.base_dir = base_dir
        
        # Check for unified master CSV first
        master_csv = None
        if master_csv_path and os.path.exists(master_csv_path):
            master_csv = master_csv_path
        else:
            csv_candidates = [
                os.path.join(base_dir, 'output', 'decision_compass_master_records.csv'),
                os.path.join(base_dir, 'data', 'shared_mcp', 'decision_compass_master_records.csv'),
                os.path.join(base_dir, 'shared_mcp', 'decision_compass_master_records.csv'),
                os.path.join(base_dir, 'data', 'decision_compass_master_records.csv'),
                os.path.join(base_dir, 'decision_compass_master_records.csv'),
                os.path.join(os.getcwd(), 'output', 'decision_compass_master_records.csv'),
                os.path.join(os.getcwd(), 'data', 'shared_mcp', 'decision_compass_master_records.csv'),
                os.path.join(os.getcwd(), 'decision_compass_master_records.csv'),
                '/content/data/data/shared_mcp/decision_compass_master_records.csv',
                '/content/data/shared_mcp/decision_compass_master_records.csv',
                '/content/data/decision_compass_master_records.csv',
            ]
            master_csv = next((p for p in csv_candidates if os.path.exists(p)), None)
            
            if not master_csv:
                import glob
                for r_dir in [base_dir, os.getcwd(), '/content/data', '/content']:
                    if os.path.exists(r_dir):
                        matches = glob.glob(os.path.join(r_dir, '**', 'decision_compass_master_records.csv'), recursive=True)
                        if matches:
                            master_csv = matches[0]
                            break
        
        if master_csv and os.path.exists(master_csv):
            import pandas as pd
            df = pd.read_csv(master_csv)
            self.recs_trans = df[df['setup_family'] == 'transition'].to_dict('records')
            self.recs_pure = df[df['setup_family'] == 'pure_trend'].to_dict('records')
            self.recs_king = df[df['setup_family'] == 'king_trend'].to_dict('records')
            self.source = f"CSV: {os.path.basename(master_csv)} ({os.path.abspath(master_csv)})"
        else:
            def find_html(name):
                p_cands = [
                    os.path.join(base_dir, 'output', name),
                    os.path.join(base_dir, 'data', 'shared_mcp', name),
                    os.path.join(base_dir, 'shared_mcp', name),
                    os.path.join(base_dir, name),
                    os.path.join(os.getcwd(), 'output', name),
                    os.path.join(os.getcwd(), name),
                    f'/content/data/data/shared_mcp/{name}',
                    f'/content/data/shared_mcp/{name}',
                ]
                for p in p_cands:
                    if os.path.exists(p): return p
                import glob
                for r_dir in [base_dir, os.getcwd(), '/content']:
                    if os.path.exists(r_dir):
                        m = glob.glob(os.path.join(r_dir, '**', name), recursive=True)
                        if m: return m[0]
                return os.path.join(base_dir, name)
            self.recs_trans = parse_html_records(find_html('dual_semicircle_decision_compass.html'))
            self.recs_pure = parse_html_records(find_html('dual_semicircle_decision_compass_new2p.html'))
            self.recs_king = parse_html_records(find_html('dual_semicircle_king_trend.html'))
            self.source = "HTML fallback"
            
        if not self.recs_trans or len(self.recs_trans) == 0:
            raise FileNotFoundError(f"[!] FATAL: DynamicCompassEngine could not find valid compass calibration records in {base_dir}! Ensure backtest_runtime_pack.zip is unzipped.")


    def compute_all_6_setups(self, is_bull=True, fg_tier='Neutral',
                             stats_old_l=None, stats_old_s=None,
                             stats_new_l=None, stats_new_s=None,
                             stats_kt_l=None, stats_kt_s=None):
        mt = 'bull' if is_bull else 'non_bull'
        
        # 1. Transition Long
        q_old_l = stats_old_l['q_label'] if stats_old_l else 'Q4'
        box_old_l = (stats_old_l.get('box_type') == 'Short (Squeeze)') if stats_old_l else False
        res1 = compute_cell_stat(self.recs_trans, mt, fg_tier, q_old_l, box_old_l, 'long')
        
        # 2. Transition Short
        q_old_s = stats_old_s['q_label'] if stats_old_s else 'Q1'
        box_old_s = (stats_old_s.get('box_type') == 'Short (Squeeze)') if stats_old_s else True
        res2 = compute_cell_stat(self.recs_trans, mt, fg_tier, q_old_s, box_old_s, 'short')
        
        # 3. Pure Bull (+++)
        q_new_l = stats_new_l['q_label'] if stats_new_l else 'Q1'
        box_new_l = (stats_new_l.get('box_type') == 'Short (Squeeze)') if stats_new_l else False
        res3 = compute_cell_stat(self.recs_pure, mt, fg_tier, q_new_l, box_new_l, 'long')
        
        # 4. Pure Bear (---)
        q_new_s = stats_new_s['q_label'] if stats_new_s else 'Q4'
        box_new_s = (stats_new_s.get('box_type') == 'Short (Squeeze)') if stats_new_s else True
        res4 = compute_cell_stat(self.recs_pure, mt, fg_tier, q_new_s, box_new_s, 'short')
        
        # 5. King Trend Long
        q_kt_l = stats_kt_l['q_label'] if stats_kt_l else 'Q4'
        box_kt_l = (stats_kt_l.get('box_type') == 'Short (Squeeze)') if stats_kt_l else True
        res5 = compute_cell_stat(self.recs_king, mt, fg_tier, q_kt_l, box_kt_l, 'long')
        
        # 6. King Trend Short
        q_kt_s = stats_kt_s['q_label'] if stats_kt_s else 'Q1'
        box_kt_s = (stats_kt_s.get('box_type') == 'Short (Squeeze)') if stats_kt_s else True
        res6 = compute_cell_stat(self.recs_king, mt, fg_tier, q_kt_s, box_kt_s, 'short')
        
        table_rows = [
            {
                'id': 1, 'name': 'Transition Setups', 'sub': 'Long (L1+L2)', 'dir': 'Long',
                'q': q_old_l, 'box': 'กล่องสั้น' if box_old_l else 'กล่องยาว',
                'win_norm': res1['win'], 'ret_norm': res1['ret'],
                'inv_name': 'Inverse Long (ดักย่อ/กลับหน้า)',
                'win_inv': 100.0 - res1['win'], 'ret_inv': -res1['ret'],
                'days': res1['days']
            },
            {
                'id': 2, 'name': 'Transition Setups', 'sub': 'Short (S1+S2)', 'dir': 'Short',
                'q': q_old_s, 'box': 'กล่องสั้น' if box_old_s else 'กล่องยาว',
                'win_norm': res2['win'], 'ret_norm': res2['ret'],
                'inv_name': 'Inverse Short (ดักเด้งสวนทาง)',
                'win_inv': 100.0 - res2['win'], 'ret_inv': -res2['ret'],
                'days': res2['days']
            },
            {
                'id': 3, 'name': 'Pure Trend Setups', 'sub': 'Long (+++)', 'dir': 'Long (+++)',
                'q': q_new_l, 'box': 'กล่องสั้น' if box_new_l else 'กล่องยาว',
                'win_norm': res3['win'], 'ret_norm': res3['ret'],
                'inv_name': 'Inverse Short',
                'win_inv': 100.0 - res3['win'], 'ret_inv': -res3['ret'],
                'days': res3['days']
            },
            {
                'id': 4, 'name': 'Pure Trend Setups', 'sub': 'Short (---)', 'dir': 'Short (---)',
                'q': q_new_s, 'box': 'กล่องสั้น' if box_new_s else 'กล่องยาว',
                'win_norm': res4['win'], 'ret_norm': res4['ret'],
                'inv_name': 'Inverse Long (ดัก Short Squeeze)',
                'win_inv': 100.0 - res4['win'], 'ret_inv': -res4['ret'],
                'days': res4['days']
            },
            {
                'id': 5, 'name': 'King Trend Hybrid', 'sub': 'Long Timing', 'dir': 'Long',
                'q': q_kt_l, 'box': 'กล่องสั้น' if box_kt_l else 'กล่องยาว',
                'win_norm': res5['win'], 'ret_norm': res5['ret'],
                'inv_name': 'Inverse Short',
                'win_inv': 100.0 - res5['win'], 'ret_inv': -res5['ret'],
                'days': res5['days']
            },
            {
                'id': 6, 'name': 'King Trend Hybrid', 'sub': 'Short Timing', 'dir': 'Short',
                'q': q_kt_s, 'box': 'กล่องสั้น' if box_kt_s else 'กล่องยาว',
                'win_norm': res6['win'], 'ret_norm': res6['ret'],
                'inv_name': 'Inverse Long (ดัก Squeeze)',
                'win_inv': 100.0 - res6['win'], 'ret_inv': -res6['ret'],
                'days': res6['days']
            }
        ]
        
        long_rets = [
            round(res1['ret'], 2),       # Transition Long Normal
            round(-res2['ret'], 2),      # Transition Short INVERSE
            round(res3['ret'], 2),       # Pure Bull Long Normal
            round(-res4['ret'], 2),      # Pure Bear INVERSE
            round(res5['ret'], 2),       # King Long Normal
            round(-res6['ret'], 2)       # King Short INVERSE
        ]
        short_rets = [-r for r in long_rets]
        
        return table_rows, long_rets, short_rets
