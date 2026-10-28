import os
import sys
import glob
import time
import shutil
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
from scipy import stats

# Set UTF-8 encoding for console output (Safe for Jupyter / Colab)
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass


def get_positions_data_range(start_date='2026-07-10', end_date=None, data_dir=r'output/monte_carlo_portfolio/data/position'):
    files = sorted(glob.glob(os.path.join(data_dir, '*.csv')))
    if not files:
        print(f"No CSV files found in {data_dir}")
        return None

    records = []
    for f in files:
        date_str = os.path.splitext(os.path.basename(f))[0]
        if date_str < start_date or (end_date and date_str > end_date):
            continue
            
        try:
            df = pd.read_csv(f)
        except Exception:
            continue
            
        df.columns = [c.strip() for c in df.columns]
        for col in ['ema50', 'ema200', 'trend']:
            if col in df.columns:
                df[col] = df[col].astype(str).str.strip()
            else:
                df[col] = ''
                
        # Ignore unpopulated/dummy position files (e.g. created before market open/trading settles)
        valid_trends = int(((df['trend'] == '+') | (df['trend'] == '-')).sum())
        if valid_trends == 0:
            continue
                
        # 1. Old Parameters: Transition Setups
        # Long Transition: Trend+ but pulling back to/below EMA50 (L1 + L2)
        l1 = int(((df['ema50'] == '-') & (df['ema200'] == '-') & (df['trend'] == '+')).sum())
        l2 = int(((df['ema50'] == '-') & (df['ema200'] == '+') & (df['trend'] == '+')).sum())
        old_long = l1 + l2
        
        # Short Transition: Trend- but bouncing to/above EMA50 (S1 + S2)
        s1 = int(((df['ema50'] == '+') & (df['ema200'] == '+') & (df['trend'] == '-')).sum())
        s2 = int(((df['ema50'] == '+') & (df['ema200'] == '-') & (df['trend'] == '-')).sum())
        old_short = s1 + s2
        
        # 2. New Parameters: Pure Trend (King #1 Edition)
        # Left Gauge (+ + +): EMA50+ EMA200+ Trend+ (Full Bull)
        new_long = int(((df['ema50'] == '+') & (df['ema200'] == '+') & (df['trend'] == '+')).sum())
        
        # Right Gauge (- - -): EMA50- EMA200- Trend- (Full Bear)
        new_short = int(((df['ema50'] == '-') & (df['ema200'] == '-') & (df['trend'] == '-')).sum())
        
        records.append({
            'Date': date_str,
            'Old_Long': old_long,
            'Old_Short': old_short,
            'New_Long': new_long,
            'New_Short': new_short,
            # Backward compatibility aliases
            'Plus3_Bull': new_long,
            'Minus3_Bear': new_short,
            'Long_Transition': old_long,
            'Short_Transition': old_short
        })

    df_summary = pd.DataFrame(records)
    df_summary = df_summary.sort_values(by='Date', ascending=True).reset_index(drop=True)
    return df_summary

def calc_stats_20d(arr, cur, median_baseline=None):
    q25 = float(np.percentile(arr, 25))
    med = float(np.median(arr))
    q75 = float(np.percentile(arr, 75))
    iqr = float(q75 - q25)
    min_v = float(np.min(arr))
    max_v = float(np.max(arr))
    pct = float(stats.percentileofscore(arr, cur, kind='weak'))
    
    if cur >= q75:
        zone = "Max Zone / Q4"
        q_label = "Q4"
    elif cur >= med:
        zone = "Mid-High / Q3"
        q_label = "Q3"
    elif cur >= q25:
        zone = "Mid-Low / Q2"
        q_label = "Q2"
    else:
        zone = "Low Zone / Q1"
        q_label = "Q1"
        
    res = {
        'min': min_v, 'q25': q25, 'median': med, 'q75': q75, 'iqr': iqr, 'max': max_v,
        'latest': cur, 'pct': pct, 'zone': zone, 'q_label': q_label
    }
    if median_baseline is not None:
        res['box_type'] = 'Short (Squeeze)' if iqr <= median_baseline else 'Tall (Dispersion)'
        res['thai_box'] = 'กล่องสั้น (Squeeze)' if iqr <= median_baseline else 'กล่องยาว (Dispersion)'
    return res

def generate_comparison_boxplot(df_range, start_date='2026-07-10', output_dir='output'):
    os.makedirs(output_dir, exist_ok=True)
    
    n_days = len(df_range)
    latest_date = df_range['Date'].iloc[-1]
    first_date = df_range['Date'].iloc[0]
    
    # 20-Day Rolling Window
    w20 = df_range.iloc[-min(20, len(df_range)):].copy()
    n_rolling = len(w20)
    
    # 6 Data Series across 3 Pairs
    data_old_l = w20['Old_Long'].values
    data_old_s = w20['Old_Short'].values
    data_new_l = w20['New_Long'].values
    data_new_s = w20['New_Short'].values
    data_kt_l = w20['Old_Long'].values     # King Trend Long Timing
    data_kt_s = w20['Old_Short'].values    # King Trend Short Timing
    
    latest_old_l = int(data_old_l[-1])
    latest_old_s = int(data_old_s[-1])
    latest_new_l = int(data_new_l[-1])
    latest_new_s = int(data_new_s[-1])
    latest_kt_l = int(data_kt_l[-1])
    latest_kt_s = int(data_kt_s[-1])
    
    stats_old_l = calc_stats_20d(data_old_l, latest_old_l, median_baseline=14.8)
    stats_old_s = calc_stats_20d(data_old_s, latest_old_s, median_baseline=15.5)
    stats_new_l = calc_stats_20d(data_new_l, latest_new_l, median_baseline=14.5)
    stats_new_s = calc_stats_20d(data_new_s, latest_new_s, median_baseline=37.8)
    stats_kt_l = calc_stats_20d(data_kt_l, latest_kt_l, median_baseline=30.7)
    stats_kt_s = calc_stats_20d(data_kt_s, latest_kt_s, median_baseline=14.2)
    
    stats_old_l['compass_20d'] = stats_old_l
    stats_old_s['compass_20d'] = stats_old_s
    stats_new_l['compass_20d'] = stats_new_l
    stats_new_s['compass_20d'] = stats_new_s
    stats_kt_l['compass_20d'] = stats_kt_l
    stats_kt_s['compass_20d'] = stats_kt_s
    
    # Academic Light Theme Styling (matching user's quantitative performance report theme)
    plt.rcParams["font.sans-serif"] = ["Tahoma", "Segoe UI", "DejaVu Sans"]
    plt.rcParams["font.family"] = "sans-serif"
    
    fig, ax = plt.subplots(figsize=(15.5, 8.5), dpi=300)
    fig.patch.set_facecolor('#ffffff')
    ax.set_facecolor('#f8fafc')
    
    positions = [1.0, 2.2, 3.8, 5.0]
    all_data = [data_old_l, data_old_s, data_new_l, data_new_s]
    latest_vals = [latest_old_l, latest_old_s, latest_new_l, latest_new_s]
    all_stats = [stats_old_l, stats_old_s, stats_new_l, stats_new_s]
    
    # Create Boxplots
    bp = ax.boxplot(all_data, positions=positions, vert=True, patch_artist=True,
                    widths=0.48, showmeans=False,
                    medianprops=dict(color='#0f172a', linewidth=2.8),
                    whiskerprops=dict(color='#64748b', linewidth=1.5, linestyle='-'),
                    capprops=dict(color='#64748b', linewidth=1.8),
                    flierprops=dict(marker='o', markeredgecolor='#94a3b8', markerfacecolor='none', markersize=4))
                    
    # Academic Pastel Box Colors (Long = Soft Mint/Emerald Green, Short = Soft Salmon/Coral Red)
    box_colors = ['#a7f3d0', '#fecaca', '#86efac', '#fca5a5']
    edge_colors = ['#059669', '#dc2626', '#16a34a', '#ef4444']
    
    for patch, bg, edge in zip(bp['boxes'], box_colors, edge_colors):
        patch.set_facecolor(bg)
        patch.set_alpha(0.75)
        patch.set_edgecolor(edge)
        patch.set_linewidth(1.8)
        
    # Jittered scatter points for the 20 historical days
    np.random.seed(42)
    for pos, arr, edge in zip(positions, all_data, edge_colors):
        jitter = np.random.normal(0, 0.04, size=len(arr))
        ax.scatter(pos + jitter, arr, color=edge, alpha=0.75, s=38, zorder=3, edgecolors='#ffffff', linewidth=0.6)
        
    # Highlight Latest Date Points with outer ring & solid center
    for pos, cur, edge in zip(positions, latest_vals, edge_colors):
        # Outer ring
        ax.scatter(pos, cur, s=280, facecolors='none', edgecolors=edge, linewidth=2.4, alpha=0.95, zorder=6)
        # Inner solid dot
        ax.scatter(pos, cur, s=65, color='#0f172a', zorder=7)
        
    # Vertical Dashed Center Separators between the 2 Models
    ax.axvline(x=3.0, color='#cbd5e1', linestyle='--', linewidth=1.4, alpha=0.9, zorder=2)
    
    # Section Header Labels at Top
    ax.text(1.6, 138, "TRANSITION SETUPS (Gauge 1)",
            fontsize=11.5, fontweight='bold', color='#0f766e', horizontalalignment='center', zorder=5)
    ax.text(4.4, 138, "PURE TREND SETUPS (Gauge 2)",
            fontsize=11.5, fontweight='bold', color='#15803d', horizontalalignment='center', zorder=5)
            
    # Floating Pill Badges above each current day point
    # Box 1: Long Transition
    ax.annotate(f"{latest_old_l} ({stats_old_l['pct']:.0f}%) [{stats_old_l['q_label']}]",
                xy=(positions[0], latest_old_l),
                xytext=(positions[0], latest_old_l + 7.5),
                fontsize=9.0, fontweight='bold', color='#065f46', horizontalalignment='center',
                bbox=dict(boxstyle="round,pad=0.4", fc="#ffffff", ec='#059669', lw=1.5, alpha=0.95),
                arrowprops=dict(arrowstyle="->", color='#059669', lw=1.6), zorder=8)
                
    # Box 2: Short Transition
    ax.annotate(f"{latest_old_s} ({stats_old_s['pct']:.0f}%) [{stats_old_s['q_label']}]",
                xy=(positions[1], latest_old_s),
                xytext=(positions[1], latest_old_s + 7.5),
                fontsize=9.0, fontweight='bold', color='#991b1b', horizontalalignment='center',
                bbox=dict(boxstyle="round,pad=0.4", fc="#ffffff", ec='#dc2626', lw=1.5, alpha=0.95),
                arrowprops=dict(arrowstyle="->", color='#dc2626', lw=1.6), zorder=8)
                
    # Box 3: + + + Full Bull
    ax.annotate(f"{latest_new_l} ({stats_new_l['pct']:.0f}%) [{stats_new_l['q_label']}]",
                xy=(positions[2], latest_new_l),
                xytext=(positions[2], latest_new_l + 7.5),
                fontsize=9.0, fontweight='bold', color='#166534', horizontalalignment='center',
                bbox=dict(boxstyle="round,pad=0.4", fc="#ffffff", ec='#16a34a', lw=1.5, alpha=0.95),
                arrowprops=dict(arrowstyle="->", color='#16a34a', lw=1.6), zorder=8)
                
    # Box 4: - - - Full Bear
    ax.annotate(f"{latest_new_s} ({stats_new_s['pct']:.0f}%) [{stats_new_s['q_label']}]",
                xy=(positions[3], latest_new_s),
                xytext=(positions[3], latest_new_s + 7.5),
                fontsize=9.0, fontweight='bold', color='#b91c1c', horizontalalignment='center',
                bbox=dict(boxstyle="round,pad=0.4", fc="#ffffff", ec='#ef4444', lw=1.5, alpha=0.95),
                arrowprops=dict(arrowstyle="->", color='#ef4444', lw=1.6), zorder=8)

    # Grid & Axis formatting
    ax.grid(axis='y', linestyle='--', alpha=0.5, color='#cbd5e1')
    ax.set_axisbelow(True)
    
    # X-axis ticks & labels with IQR and Q1-Q3 range
    ax.set_xticks(positions)
    ax.set_xticklabels([
        f"LONG (Transition)\nIQR: {stats_old_l['iqr']:.1f} ({stats_old_l['thai_box']})",
        f"SHORT (Transition)\nIQR: {stats_old_s['iqr']:.1f} ({stats_old_s['thai_box']})",
        f"+ + + (Pure Bull)\nIQR: {stats_new_l['iqr']:.1f} ({stats_new_l['thai_box']})",
        f"- - - (Pure Bear)\nIQR: {stats_new_s['iqr']:.1f} ({stats_new_s['thai_box']})"
    ], fontsize=10.0, fontweight='bold', color='#1e293b')
    
    ax.tick_params(axis='x', colors='#334155', pad=8)
    ax.tick_params(axis='y', colors='#475569')
    ax.set_xlim(0.3, 5.7)
    ax.set_ylim(0, 150)
    
    # Title & Subtitle (Crisp Dark Academic Style)
    fig.text(0.04, 0.95, "Quantitative Trend Alignment Report — 20-Day Rolling Quantiles Box Comparison",
             fontsize=14.5, fontweight='bold', color='#0f172a')
    fig.text(0.04, 0.92, f"การกระจายตัว 20 วันย้อนหลัง ({w20['Date'].iloc[0]} ถึง {latest_date}): เส้นกลางคือ Median, กรอบกล่องคือ Q1 - Q3 (IQR), และจุดวงกลมเข้มคือ Current Day ({latest_date})",
             fontsize=10.0, color='#475569')

    # Footnote Banner explaining Gauge 3 relationship
    note_text = "📌 หมายเหตุ: เกจที่ 3 (King Trend) ใช้ชุดข้อมูลการกระจายตัวร่วมกับเกจที่ 1 (Transition Setups) โดยทำหน้าที่ประเมินแต้มต่อ Win Rate และ Avg Return เพิ่มเติมสำหรับกลุ่ม King Long (Hurdle >= 60.0%)"
    fig.text(0.5, 0.02, note_text, fontsize=9.5, color='#1e293b', style='italic', horizontalalignment='center',
             bbox=dict(boxstyle='round,pad=0.5', facecolor='#f1f5f9', edgecolor='#cbd5e1', alpha=0.9))
             
    # Legend Top Right (Academic Pill Badge)
    fig.text(0.96, 0.94, f"จุดข้อมูล: 20 วันย้อนหลัง | วันล่าสุด: {latest_date}",
             fontsize=9.5, fontweight='semibold', color='#0f172a', horizontalalignment='right',
             bbox=dict(boxstyle="round,pad=0.35", fc="#f1f5f9", ec="#cbd5e1", lw=1.2))

    # Spines styling
    for spine in ax.spines.values():
        spine.set_color('#cbd5e1')
        spine.set_linewidth(1.2)
        
    plt.tight_layout(rect=[0.01, 0.05, 0.99, 0.90])
    
    timestamp = int(time.time())
    png_path = os.path.join(output_dir, f'trend_alignment_comparison_boxplot_from_{first_date}_{timestamp}.png')
    static_png_path = os.path.join(output_dir, f'trend_alignment_comparison_boxplot_from_{first_date}.png')
    
    fig.savefig(png_path, bbox_inches='tight', facecolor=fig.get_facecolor(), edgecolor='none')
    fig.savefig(static_png_path, bbox_inches='tight', facecolor=fig.get_facecolor(), edgecolor='none')
    plt.close(fig)
    print(f"Saved 4-Box Comparison BoxPlot PNG to {png_path} and {static_png_path}")
            
    return png_path, stats_old_l, stats_old_s, stats_new_l, stats_new_s, stats_kt_l, stats_kt_s, n_days

if __name__ == '__main__':
    df_range = get_positions_data_range(start_date='2026-07-10', end_date=None)
    if df_range is not None:
        res = generate_comparison_boxplot(df_range, start_date='2026-07-10')
        png_path = res[0]
        print("Done!")


