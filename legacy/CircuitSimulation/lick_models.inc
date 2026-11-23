* HydraPurr lick sensor - device models (shared by .cir decks and the .asc)
.model Q2N2222 NPN(IS=14.34f XTI=3 EG=1.11 VAF=74.03 BF=255.9 NE=1.307
+ ISE=14.34f IKF=.2847 XTB=1.5 BR=6.092 NC=2 ISC=0 IKR=0 RC=1
+ RB=10 RE=0 CJC=7.306p MJC=.3416 VJC=.75 FC=.5 CJE=22.01p
+ TR=46.91n TF=411.1p ITF=.6 VTF=1.7 XTF=3)
.model DLED  D(Is=1e-19 N=1.9 Rs=2)
.model Dprot D(Is=1e-12 N=1.0 Rs=0.5)

* PC817 / ORPC-817C optocoupler (LED in, saturating BJT out)
.subckt PC817 A K C E
Vs   A AA 0
Dled AA K Dopto
Fb   0 b Vs 0.02
Qo   C b E QNPNL
.model Dopto D(Is=1e-14 N=1.8 Rs=10)
.model QNPNL NPN(BF=200 IS=1e-14)
.ends
