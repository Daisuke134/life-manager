"""架空の損失と分布の教材。GAN学習・実人口評価ではない。"""
import math, json
p=[.4,.2,.1,.3]; collapsed=[1.,0.,0.,0.]
loss=lambda d:-math.log(d)
assert loss(.1)>loss(.8)
assert math.isclose(sum(p),1.)
r={'mode':'fictional_algebra_only','training_run':False,'generator_loss_at_D_0_1':loss(.1),'generator_loss_at_D_0_8':loss(.8),'collapsed_distribution_total_variation':.5*sum(abs(a-b) for a,b in zip(p,collapsed))}
print(json.dumps(r,indent=2))
