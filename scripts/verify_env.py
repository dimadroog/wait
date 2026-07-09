"""Проверка ML-окружения после setup_venv.ps1."""
import sys

def main() -> None:
    print(f"Python {sys.version}")
    import numpy
    import torch
    import gymnasium
    import stable_baselines3
    import cv2
    import yaml

    print(f"numpy {numpy.__version__}")
    print(f"torch {torch.__version__} (cuda={torch.cuda.is_available()})")
    print(f"gymnasium {gymnasium.__version__}")
    print(f"stable-baselines3 {stable_baselines3.__version__}")
    print(f"opencv {cv2.__version__}")
    print("OK")

if __name__ == "__main__":
    main()
