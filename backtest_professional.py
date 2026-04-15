"""
Professional Backtester

Runs the professional CVD + Liquidity + Market Structure strategy
"""

import pandas as pd
import numpy as np
import json
from datetime import datetime
import config_professional as config
from indicators_professional import ProfessionalIndicators
from strategy_professional import ProfessionalStrategy
import matplotlib.pyplot as plt
import seaborn as sns


class ProfessionalBacktester:
    """Backtest professional trading strategy"""

    def __init__(self, data_file=None, leverage=5, capital=7500):
        self.data_file = data_file
        self.leverage = leverage
        self.initial_capital = capital
        self.df = None
        self.trades = []
        self.equity_curve = []

    def load_data(self):
        """Load historical data"""
        # Determine data file based on timeframe
        if self.data_file:
            data_file = self.data_file
        elif config.TIMEFRAME == '4h':
            data_file = f'{config.DATA_DIR}/eth_usd_240m_{config.LOOKBACK_DAYS}d.csv'
        elif config.TIMEFRAME == '1d':
            data_file = f'{config.DATA_DIR}/eth_usd_1440m_{config.LOOKBACK_DAYS}d.csv'
        else:  # 1h
            data_file = f'{config.DATA_DIR}/eth_usd_60m_{config.LOOKBACK_DAYS}d.csv'

        print(f"Loading data from {data_file}...")
        self.df = pd.read_csv(data_file)
        self.df['timestamp'] = pd.to_datetime(self.df['timestamp'])
        print(f"✅ Loaded {len(self.df)} candles")
        print(f"📅 Date range: {self.df.iloc[0]['timestamp']} to {self.df.iloc[-1]['timestamp']}")

        return self.df

    def prepare_data(self):
        """Calculate all indicators"""
        print("\n" + "=" * 70)
        print("CALCULATING PROFESSIONAL INDICATORS")
        print("=" * 70)

        self.df = ProfessionalIndicators.add_all_indicators(self.df, timeframe=config.TIMEFRAME)

        # Validate data quality
        is_valid, missing, error_msg = ProfessionalIndicators.validate_data_quality(self.df)

        if not is_valid:
            print(f"\n❌ DATA QUALITY ERROR: {error_msg}")
            raise ValueError("Data quality check failed")

        print("✅ All indicators calculated and validated")

    def run_backtest(self):
        """Execute backtest"""
        print("\n" + "=" * 70)
        print("RUNNING PROFESSIONAL BACKTEST")
        print("=" * 70)
        print(f"💰 Initial Capital: ${self.initial_capital:,.2f}")
        print(f"⚡ Leverage: {self.leverage}x")
        print(f"🎯 Risk Per Trade: {config.RISK_PER_TRADE_PCT}%")
        print(f"📊 Min Confluence: {config.MIN_CONFLUENCE_SCORE}")
        print("=" * 70 + "\n")

        # Initialize strategy
        strategy = ProfessionalStrategy(
            leverage=self.leverage,
            capital=self.initial_capital,
            risk_pct=config.RISK_PER_TRADE_PCT
        )

        # Run strategy
        self.trades = strategy.run(self.df)

        # Track equity curve
        capital = self.initial_capital
        self.equity_curve = [{'timestamp': self.df.iloc[0]['timestamp'], 'equity': capital}]

        for trade in self.trades:
            if trade['action'] == 'EXIT':
                capital = strategy.capital
                self.equity_curve.append({
                    'timestamp': trade['timestamp'],
                    'equity': capital
                })

        completed_trades = len([t for t in self.trades if t['action'] == 'EXIT'])
        print(f"\n✅ Backtest complete! Executed {completed_trades} trades")

    def calculate_metrics(self):
        """Calculate comprehensive performance metrics"""
        exit_trades = [t for t in self.trades if t['action'] == 'EXIT']

        if not exit_trades:
            print("\n❌ No trades executed!")
            return None

        # Basic metrics
        total_trades = len(exit_trades)
        winning_trades = [t for t in exit_trades if t['net_pnl'] > 0]
        losing_trades = [t for t in exit_trades if t['net_pnl'] <= 0]

        win_rate = len(winning_trades) / total_trades * 100 if total_trades > 0 else 0

        total_pnl = sum(t['net_pnl'] for t in exit_trades)
        gross_profit = sum(t['net_pnl'] for t in winning_trades) if winning_trades else 0
        gross_loss = abs(sum(t['net_pnl'] for t in losing_trades)) if losing_trades else 0

        avg_win = np.mean([t['net_pnl'] for t in winning_trades]) if winning_trades else 0
        avg_loss = np.mean([t['net_pnl'] for t in losing_trades]) if losing_trades else 0

        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')

        # Equity curve analysis
        equity_df = pd.DataFrame(self.equity_curve)
        final_equity = equity_df.iloc[-1]['equity']
        total_return_pct = (final_equity - self.initial_capital) / self.initial_capital * 100

        # Drawdown analysis
        equity_df['peak'] = equity_df['equity'].cummax()
        equity_df['drawdown'] = (equity_df['equity'] - equity_df['peak']) / equity_df['peak'] * 100
        max_drawdown = equity_df['drawdown'].min()

        # Sharpe ratio
        returns = equity_df['equity'].pct_change().dropna()
        if len(returns) > 0 and returns.std() > 0:
            sharpe_ratio = (returns.mean() / returns.std()) * np.sqrt(365 * 24)
        else:
            sharpe_ratio = 0

        # Hold time analysis
        hold_times = [t['hold_time_hours'] for t in exit_trades]
        avg_hold_time = np.mean(hold_times) if hold_times else 0

        # Exit reason analysis
        exit_reasons = {}
        for t in exit_trades:
            reason = t['exit_reason']
            exit_reasons[reason] = exit_reasons.get(reason, 0) + 1

        # Confluence score analysis
        entry_trades = [t for t in self.trades if t['action'] == 'ENTER']
        confluence_scores = [t.get('confluence_score', 0) for t in entry_trades]
        avg_confluence = np.mean(confluence_scores) if confluence_scores else 0

        # Win rate by confluence score
        win_rate_by_confluence = {}
        for score in range(3, 8):
            trades_at_score = [t for t in exit_trades
                             if any(e.get('confluence_score') == score
                                   for e in self.trades
                                   if e['action'] == 'ENTER' and e['timestamp'] == t['timestamp'])]
            if trades_at_score:
                wins = len([t for t in trades_at_score if t['net_pnl'] > 0])
                win_rate_by_confluence[score] = (wins / len(trades_at_score)) * 100

        metrics = {
            'total_trades': total_trades,
            'winning_trades': len(winning_trades),
            'losing_trades': len(losing_trades),
            'win_rate': win_rate,
            'total_pnl': total_pnl,
            'gross_profit': gross_profit,
            'gross_loss': gross_loss,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'profit_factor': profit_factor,
            'initial_capital': self.initial_capital,
            'final_equity': final_equity,
            'total_return_pct': total_return_pct,
            'max_drawdown': max_drawdown,
            'sharpe_ratio': sharpe_ratio,
            'avg_hold_time_hours': avg_hold_time,
            'exit_reasons': exit_reasons,
            'avg_confluence_score': avg_confluence,
            'win_rate_by_confluence': win_rate_by_confluence,
            'leverage': self.leverage
        }

        return metrics

    def print_results(self, metrics):
        """Print comprehensive backtest results"""
        print("\n" + "=" * 70)
        print("🎯 PROFESSIONAL STRATEGY BACKTEST RESULTS")
        print("=" * 70)

        print(f"\n📊 TRADING PERFORMANCE:")
        print(f"  Total Trades: {metrics['total_trades']}")
        print(f"  Winning Trades: {metrics['winning_trades']} ✅")
        print(f"  Losing Trades: {metrics['losing_trades']} ❌")
        print(f"  Win Rate: {metrics['win_rate']:.2f}%")
        print(f"  Average Confluence Score: {metrics['avg_confluence_score']:.1f}/7")

        if metrics['win_rate_by_confluence']:
            print(f"\n  📈 Win Rate by Confluence Score:")
            for score in sorted(metrics['win_rate_by_confluence'].keys()):
                wr = metrics['win_rate_by_confluence'][score]
                print(f"     Score {score}: {wr:.1f}%")

        print(f"\n💰 PROFITABILITY:")
        print(f"  Initial Capital: ${metrics['initial_capital']:,.2f}")
        print(f"  Final Equity: ${metrics['final_equity']:,.2f}")
        print(f"  Total P&L: ${metrics['total_pnl']:,.2f}")
        print(f"  Total Return: {metrics['total_return_pct']:.2f}%")
        print(f"  Gross Profit: ${metrics['gross_profit']:,.2f}")
        print(f"  Gross Loss: ${metrics['gross_loss']:,.2f}")
        print(f"  Profit Factor: {metrics['profit_factor']:.2f}")

        print(f"\n📈 RISK METRICS:")
        print(f"  Max Drawdown: {metrics['max_drawdown']:.2f}%")
        print(f"  Sharpe Ratio: {metrics['sharpe_ratio']:.2f}")
        print(f"  Average Win: ${metrics['avg_win']:,.2f}")
        print(f"  Average Loss: ${metrics['avg_loss']:,.2f}")
        print(f"  Risk/Reward: 1:{abs(metrics['avg_win']/metrics['avg_loss']):.2f}" if metrics['avg_loss'] != 0 else "  Risk/Reward: N/A")

        print(f"\n⏱️  TRADE DURATION:")
        print(f"  Average Hold Time: {metrics['avg_hold_time_hours']:.1f} hours ({metrics['avg_hold_time_hours']/24:.1f} days)")

        print(f"\n🚪 EXIT REASONS:")
        for reason, count in sorted(metrics['exit_reasons'].items(), key=lambda x: x[1], reverse=True):
            pct = (count / metrics['total_trades']) * 100
            print(f"  {reason}: {count} ({pct:.1f}%)")

        print("\n" + "=" * 70)

        # Performance evaluation
        print("\n🎖️  PERFORMANCE EVALUATION:")

        if metrics['win_rate'] >= 40 and metrics['profit_factor'] >= 1.5:
            print("  ✅ EXCELLENT - Strategy meets professional standards")
        elif metrics['win_rate'] >= 35 and metrics['profit_factor'] >= 1.2:
            print("  ✓ GOOD - Strategy is profitable, room for improvement")
        elif metrics['profit_factor'] > 1.0:
            print("  ~ MARGINAL - Strategy is barely profitable")
        else:
            print("  ❌ POOR - Strategy needs significant improvement")

        print("\n  Expected Performance Targets:")
        print(f"  Target Win Rate: 40-50% | Achieved: {metrics['win_rate']:.1f}%")
        print(f"  Target Profit Factor: >1.5 | Achieved: {metrics['profit_factor']:.2f}")
        print(f"  Target Max DD: <20% | Achieved: {metrics['max_drawdown']:.1f}%")
        print(f"  Target Sharpe: >1.5 | Achieved: {metrics['sharpe_ratio']:.2f}")

        print("\n" + "=" * 70)

    def save_results(self, metrics):
        """Save results to files"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        # Save metrics
        metrics_file = f"{config.RESULTS_DIR}/professional_metrics_{timestamp}.json"
        metrics_clean = metrics.copy()
        if np.isinf(metrics_clean.get('profit_factor', 0)):
            metrics_clean['profit_factor'] = 'inf'
        with open(metrics_file, 'w') as f:
            json.dump(metrics_clean, f, indent=4)
        print(f"\n📁 Metrics saved to {metrics_file}")

        # Save trades
        trades_file = f"{config.RESULTS_DIR}/professional_trades_{timestamp}.csv"
        trades_df = pd.DataFrame(self.trades)
        trades_df.to_csv(trades_file, index=False)
        print(f"📁 Trades saved to {trades_file}")

        # Save equity curve
        equity_file = f"{config.RESULTS_DIR}/professional_equity_{timestamp}.csv"
        equity_df = pd.DataFrame(self.equity_curve)
        equity_df.to_csv(equity_file, index=False)
        print(f"📁 Equity curve saved to {equity_file}")

        return metrics_file, trades_file, equity_file

    def plot_results(self):
        """Create visualization plots"""
        if not self.equity_curve:
            return

        fig, axes = plt.subplots(2, 2, figsize=(16, 10))
        fig.suptitle('Professional Strategy Backtest Results', fontsize=16, fontweight='bold')

        # Equity curve
        equity_df = pd.DataFrame(self.equity_curve)
        axes[0, 0].plot(equity_df['timestamp'], equity_df['equity'], linewidth=2, color='#2E86AB')
        axes[0, 0].axhline(y=self.initial_capital, color='red', linestyle='--',
                          label='Initial Capital', linewidth=1.5)
        axes[0, 0].set_title('Equity Curve', fontsize=14, fontweight='bold')
        axes[0, 0].set_xlabel('Date')
        axes[0, 0].set_ylabel('Equity ($)')
        axes[0, 0].legend()
        axes[0, 0].grid(True, alpha=0.3)

        # Drawdown
        equity_df['peak'] = equity_df['equity'].cummax()
        equity_df['drawdown'] = (equity_df['equity'] - equity_df['peak']) / equity_df['peak'] * 100
        axes[0, 1].fill_between(equity_df['timestamp'], equity_df['drawdown'], 0,
                               color='#A23B72', alpha=0.5)
        axes[0, 1].plot(equity_df['timestamp'], equity_df['drawdown'],
                       color='#A23B72', linewidth=2)
        axes[0, 1].set_title('Drawdown', fontsize=14, fontweight='bold')
        axes[0, 1].set_xlabel('Date')
        axes[0, 1].set_ylabel('Drawdown (%)')
        axes[0, 1].grid(True, alpha=0.3)

        # Trade P&L distribution
        exit_trades = [t for t in self.trades if t['action'] == 'EXIT']
        pnls = [t['net_pnl'] for t in exit_trades]
        axes[1, 0].hist(pnls, bins=30, edgecolor='black', alpha=0.7, color='#F18F01')
        axes[1, 0].axvline(x=0, color='red', linestyle='--', linewidth=2)
        axes[1, 0].set_title('Trade P&L Distribution', fontsize=14, fontweight='bold')
        axes[1, 0].set_xlabel('P&L ($)')
        axes[1, 0].set_ylabel('Frequency')
        axes[1, 0].grid(True, alpha=0.3)

        # Win/Loss pie chart
        winning = len([t for t in exit_trades if t['net_pnl'] > 0])
        losing = len([t for t in exit_trades if t['net_pnl'] <= 0])
        colors = ['#06A77D', '#D62828']
        axes[1, 1].pie([winning, losing], labels=[f'Wins ({winning})', f'Losses ({losing})'],
                      autopct='%1.1f%%', colors=colors, startangle=90,
                      textprops={'fontsize': 12, 'fontweight': 'bold'})
        axes[1, 1].set_title('Win/Loss Ratio', fontsize=14, fontweight='bold')

        plt.tight_layout()

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        plot_file = f"{config.RESULTS_DIR}/professional_plot_{timestamp}.png"
        plt.savefig(plot_file, dpi=300, bbox_inches='tight')
        print(f"📊 Plots saved to {plot_file}")

        plt.close()


def main():
    """Main backtesting function"""
    print("\n" + "=" * 70)
    print("🚀 PROFESSIONAL TRADING STRATEGY BACKTESTER")
    print("=" * 70)
    print("Strategy: CVD + Liquidity + Market Structure")
    print("Methodology: Institutional Order Flow Analysis")
    print("=" * 70)

    # Initialize backtester
    backtester = ProfessionalBacktester(
        leverage=config.LEVERAGE,
        capital=config.CAPITAL
    )

    try:
        # Load and prepare data
        backtester.load_data()
        backtester.prepare_data()

        # Run backtest
        backtester.run_backtest()

        # Calculate and display metrics
        metrics = backtester.calculate_metrics()
        if metrics:
            backtester.print_results(metrics)
            backtester.save_results(metrics)
            backtester.plot_results()

            print("\n✅ BACKTESTING COMPLETE!")
            print("\n📝 Next Steps:")
            print(f"1. Review results in {config.RESULTS_DIR}/ directory")
            print("2. Analyze confluence scores and win rates")
            print("3. Study individual trades in trade CSV file")
            print("4. Adjust parameters if needed in config_professional.py")
            print("5. Once satisfied, proceed to paper trading")
            print("\n💡 Remember: Process > Results")
            print("   Focus on following the methodology, not forcing profits")
        else:
            print("\n❌ Backtest failed - no trades executed")
            print("   Possible reasons:")
            print("   - Confluence requirements too strict")
            print("   - Not enough data/indicators")
            print("   - Check config_professional.py settings")

    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
