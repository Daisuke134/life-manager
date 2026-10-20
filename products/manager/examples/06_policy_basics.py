from manager_core.policy_basics import ips_estimate
if __name__=='__main__':
    toy_logs=[{'action':'A','reward':1,'logging_propensity':.5,'target_propensity':1},
              {'action':'B','reward':0,'logging_propensity':.5,'target_propensity':0}]*2
    print('SYNTHETIC IPS estimate:',ips_estimate(toy_logs,{'A'},{'A','B'}))
    print('Required real-world assumptions NOT certified by this computation.')
