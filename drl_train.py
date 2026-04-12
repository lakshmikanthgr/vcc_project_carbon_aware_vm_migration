"""
drl_train.py — Train a DQN agent for CALM-SLA VM migration decisions.

Usage:
  python drl_train.py                    # full 100k-step training
  python drl_train.py --steps 20000      # quick smoke-test
  python drl_train.py --eval-only        # evaluate existing model

Output:
  data/models/drl_agent.zip   — saved DQN model
  data/models/drl_agent_stats.json — training metrics
"""

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np
from stable_baselines3 import DQN
from stable_baselines3.common.env_util import make_vec_env
from stable_baselines3.common.evaluation import evaluate_policy
from stable_baselines3.common.callbacks import EvalCallback, BaseCallback

from drl_environment import CALMSLAEnv, ZONES

MODEL_PATH = Path("data/models/drl_agent")
STATS_PATH = Path("data/models/drl_agent_stats.json")


# ------------------------------------------------------------------ #
# Custom callback: prints progress every N steps
# ------------------------------------------------------------------ #
class ProgressCallback(BaseCallback):
    def __init__(self, print_freq: int = 10_000):
        super().__init__()
        self.print_freq = print_freq
        self._episode_rewards: list = []
        self._ep_reward = 0.0

    def _on_step(self) -> bool:
        reward = self.locals["rewards"][0]
        self._ep_reward += reward
        if self.locals["dones"][0]:
            self._episode_rewards.append(self._ep_reward)
            self._ep_reward = 0.0

        if self.num_timesteps % self.print_freq == 0:
            recent = self._episode_rewards[-10:] if self._episode_rewards else [0]
            mean_r = np.mean(recent)
            print(f"  [step {self.num_timesteps:>7d}] mean episode reward (last 10 eps): {mean_r:+.2f}")
        return True


# ------------------------------------------------------------------ #
# Evaluation helper
# ------------------------------------------------------------------ #
def evaluate(model: DQN, n_episodes: int = 20) -> dict:
    """Run episodes and collect per-episode stats."""
    env = CALMSLAEnv()
    episode_rewards, migrations, sla_violations = [], [], []

    for _ in range(n_episodes):
        obs, _ = env.reset()
        ep_reward, ep_migs, ep_viols = 0.0, 0, 0
        done = False
        while not done:
            action, _ = model.predict(obs, deterministic=True)
            obs, reward, terminated, truncated, info = env.step(int(action))
            done = terminated or truncated
            ep_reward += reward
            if "migrate" in info.get("action", ""):
                ep_migs += 1
            if info.get("sla_violated"):
                ep_viols += 1
        episode_rewards.append(ep_reward)
        migrations.append(ep_migs)
        sla_violations.append(ep_viols)

    return {
        "mean_reward":        float(np.mean(episode_rewards)),
        "std_reward":         float(np.std(episode_rewards)),
        "mean_migrations":    float(np.mean(migrations)),
        "mean_sla_violations":float(np.mean(sla_violations)),
        "n_episodes":         n_episodes,
    }


# ------------------------------------------------------------------ #
# Training
# ------------------------------------------------------------------ #
def train(total_steps: int = 100_000, n_envs: int = 4) -> DQN:
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*55}")
    print(f"  CALM-SLA DRL Agent Training")
    print(f"  Zones: {ZONES}")
    print(f"  Steps: {total_steps:,}   |   Parallel envs: {n_envs}")
    print(f"{'='*55}\n")

    # Vectorised training environments
    vec_env = make_vec_env(lambda: CALMSLAEnv(), n_envs=n_envs)

    model = DQN(
        "MlpPolicy",
        vec_env,
        learning_rate        = 1e-3,
        buffer_size          = 50_000,
        learning_starts      = 1_000,
        batch_size           = 64,
        gamma                = 0.99,
        train_freq           = 4,
        target_update_interval = 1_000,
        exploration_fraction = 0.3,
        exploration_final_eps= 0.05,
        policy_kwargs        = dict(net_arch=[128, 128]),
        verbose              = 0,
    )

    callback = ProgressCallback(print_freq=10_000)
    model.learn(total_timesteps=total_steps, callback=callback, progress_bar=False)

    model.save(str(MODEL_PATH))
    print(f"\n[DRL] Model saved → {MODEL_PATH}.zip")
    return model


# ------------------------------------------------------------------ #
# Entry point
# ------------------------------------------------------------------ #
def main():
    parser = argparse.ArgumentParser(description="Train or evaluate the CALM-SLA DRL agent")
    parser.add_argument("--steps",     type=int, default=100_000, help="Training timesteps")
    parser.add_argument("--eval-only", action="store_true",       help="Skip training, evaluate existing model")
    parser.add_argument("--eval-eps",  type=int, default=20,      help="Evaluation episodes")
    args = parser.parse_args()

    if args.eval_only:
        if not MODEL_PATH.with_suffix(".zip").exists():
            print(f"[ERROR] No saved model at {MODEL_PATH}.zip — run training first.")
            sys.exit(1)
        print(f"[DRL] Loading model from {MODEL_PATH}.zip ...")
        model = DQN.load(str(MODEL_PATH))
    else:
        model = train(total_steps=args.steps)

    print(f"\n[DRL] Evaluating over {args.eval_eps} episodes ...")
    stats = evaluate(model, n_episodes=args.eval_eps)

    print(f"\n{'='*55}")
    print(f"  Evaluation Results ({stats['n_episodes']} episodes)")
    print(f"{'='*55}")
    print(f"  Mean reward          : {stats['mean_reward']:+.3f}  ± {stats['std_reward']:.3f}")
    print(f"  Mean migrations/day  : {stats['mean_migrations']:.1f}")
    print(f"  Mean SLA violations  : {stats['mean_sla_violations']:.2f}")
    print(f"{'='*55}\n")

    STATS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(STATS_PATH, "w") as f:
        json.dump(stats, f, indent=2)
    print(f"[DRL] Stats saved → {STATS_PATH}")

    if not args.eval_only:
        if stats["mean_reward"] > 0:
            print("[DRL] ✓ Agent learned a profitable policy (positive mean reward)")
        else:
            print("[DRL] ⚠ Mean reward is negative — consider more steps or tuning ALPHA/BETA/GAMMA")
        if stats["mean_sla_violations"] < 1.0:
            print("[DRL] ✓ SLA violations under control (<1 per day on average)")
        else:
            print("[DRL] ⚠ SLA violations are high — GAMMA[Gold] penalty may need tuning")


if __name__ == "__main__":
    main()
