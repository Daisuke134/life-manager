"""架空の一数値の式を検算。モデル学習・推論ではない。"""
import math, json
x0=2.0
noise=-1.0
signal_coefficient=math.sqrt(.64)
noise_coefficient=math.sqrt(1-.64)
xt=signal_coefficient*x0+noise_coefficient*noise
estimate=lambda predicted_noise:(xt-noise_coefficient*predicted_noise)/signal_coefficient
assert math.isclose(xt,1.0)
assert math.isclose(estimate(noise),2.0)
assert math.isclose(estimate(-.5),1.625)
print(json.dumps({'mode':'fictional_algebra_only','trained_model':False,'x0':x0,'noise':noise,'xt':xt,'oracle_reconstruction':estimate(noise),'imperfect_reconstruction':estimate(-.5)},indent=2))
