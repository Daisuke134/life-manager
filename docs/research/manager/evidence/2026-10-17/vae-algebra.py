"""VAEの式だけの教材。学習済みモデルでも論文再現でもない。"""
import math, json
mu, sigma, epsilon = [1., -1.], [.5, 2.], [0., 1.]
z = [m+s*e for m,s,e in zip(mu,sigma,epsilon)]
def kl(mean, std):
    return .5 * (mean**2 + std**2 - 1 - math.log(std**2))
assert z == [1., 1.]
assert kl(0,1) == 0
assert kl(1,1) == .5
print(json.dumps({"mode":"fictional_algebra_only", "trained_model":False,"z":z,"kl_standard":kl(0,1),"kl_shifted_mean":kl(1,1)}, indent=2))
