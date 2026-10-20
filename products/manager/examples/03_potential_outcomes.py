from manager_core.potential_outcomes import oracle_ate,observed_only

if __name__=='__main__':
    units=[{'id':'toy-1','y0':1,'y1':3},{'id':'toy-2','y0':5,'y1':7}]
    print('SYNTHETIC ORACLE ATE',oracle_ate(units))
    print('What would actually be observed:',observed_only(units,{'toy-1':1,'toy-2':0}))
    print('In reality the missing potential outcomes are NOT known.')
