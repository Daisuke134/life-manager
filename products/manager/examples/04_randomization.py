from manager_core.randomization import toy_rct_estimate

if __name__=='__main__':
    for n in (100,1000,25000):
        print('SYNTHETIC RCT',n,toy_rct_estimate(n=n,seed=23))
    print('A numerical demonstration, not a field trial.')
