from manager_core.spillover import net_additional_resources
if __name__=='__main__':
    print('SYNTHETIC financial spillover: +100 - 90 - 20 =',net_additional_resources(100,[-90],20))
    print('This is accounting on assumed changes, not a causal estimate.')
