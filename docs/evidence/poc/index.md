# PoC evidence index

Every retained artifact under this tree, one row per file, each row
carrying the sha256 over the file's bytes. Classes:

- `generated` — regenerable by the named command; regenerating rewrites
  the artifact and this index's digest row for it.
- `record` — digest-bound records (timed demos, decision registrations);
  regenerating the index refreshes digests but NEVER rewrites a record.

The index excludes itself (a file cannot digest itself) and is
deterministic — an unchanged tree regenerates byte-identically — so it
carries no timestamp of its own.

| Artifact | Class | SHA-256 | Regeneration |
|---|---|---|---|
| `decisions/d13-async-posture.md` | record | `2cbeb143eb3510bd68164875dd4042ab6c6ddabaaf2e824f68556467b69280fa` | record — digest-bound, never regenerated |
| `decisions/deferred-deviations.md` | record | `db1a1d639ed40eb5891a48e66e21d21e22a2bc1bba1735795a2dabf2a85daa48` | record — digest-bound, never regenerated |
| `fault-matrix/junit.xml` | generated | `85b7bd7734722ac7cb5a2fd9b28173362655b7ee4758513b24cc24ed626074a5` | `benchweave evidence faults --dest docs/evidence/poc` |
| `fault-matrix/legs.json` | generated | `70aae935905ca64ffd07f567d2be55215401110f13b0e09bc28e74d2c84a35ba` | `benchweave evidence faults --dest docs/evidence/poc` |
| `runs/run-001.json` | generated | `9cf3898617ceb74c4f29bbcd79de4693656ec57369276e63510f091b857e8590` | `benchweave evidence runs --dest docs/evidence/poc` |
| `runs/run-002.json` | generated | `17ba4f5898108939f588b6915682ff91a91a0f56e06e221c20984db7dea5a19b` | `benchweave evidence runs --dest docs/evidence/poc` |
| `runs/run-003.json` | generated | `0dbe97cc9ec546f895d8bcc535f37f0077e2f7590e8a740e6bbbad75865ea21e` | `benchweave evidence runs --dest docs/evidence/poc` |
| `runs/run-004.json` | generated | `f5ba33940cf2f216f41b025c556f62b8afcd4209e0f38a307baf258caabe6881` | `benchweave evidence runs --dest docs/evidence/poc` |
| `runs/run-005.json` | generated | `3a28c7680c13522a2b6e8e8bb5285645985a4ed1b99b90142414d148948a7dd4` | `benchweave evidence runs --dest docs/evidence/poc` |
| `runs/run-006.json` | generated | `dfd945aa3e11ef957bfc07063aa7781af1643259ef35dfa1ff5bb9cfd1f06292` | `benchweave evidence runs --dest docs/evidence/poc` |
| `runs/run-007.json` | generated | `52494bd9743239bd7e4bbc6fb7839c711d045bf143efd278837490371f2fc87a` | `benchweave evidence runs --dest docs/evidence/poc` |
| `runs/run-008.json` | generated | `b3ed6eec39db066a8d8025fd2356ff38b28e4b8f65f566c443561d5503954818` | `benchweave evidence runs --dest docs/evidence/poc` |
| `runs/run-009.json` | generated | `41ab3814390542d88a09f4d100bc6fd949b4d28f37570031b525a2c866d91039` | `benchweave evidence runs --dest docs/evidence/poc` |
| `runs/run-010.json` | generated | `d72638b9c57a07dacfe4510ff0b6c43fe16f3cdfb37997a6de5359ee8e8c946a` | `benchweave evidence runs --dest docs/evidence/poc` |
| `runs/run-011.json` | generated | `d51213cb7b6adf3e6ee74cdbe629c682ceacc5ee664a0aa59705dedf7d2b2818` | `benchweave evidence runs --dest docs/evidence/poc` |
| `runs/run-012.json` | generated | `1927cee60fddccbccac536fc8b889d3caeb4947069f9c6352ac2716350caa1df` | `benchweave evidence runs --dest docs/evidence/poc` |
| `runs/run-013.json` | generated | `71bca5c3505f64a1b5cd8368350246a94d88f678641049492b3d075f23d3a596` | `benchweave evidence runs --dest docs/evidence/poc` |
| `runs/run-014.json` | generated | `05f7fc12376f89688cfb9f80d267766dc86ada19295e3abebce0f232a2accb60` | `benchweave evidence runs --dest docs/evidence/poc` |
| `runs/run-015.json` | generated | `fa231df32243dee9110f614d4332f3ea2f988e93eb46ca536a21debfa7987fb7` | `benchweave evidence runs --dest docs/evidence/poc` |
| `runs/run-016.json` | generated | `54992acd4bd4ec73e27611501775a1032a818099aaac5f1b3ca52b415a7b4ad4` | `benchweave evidence runs --dest docs/evidence/poc` |
| `runs/run-017.json` | generated | `24bc0d4c1ea83564a16e97973e96bf10866350fed400415775ea94beeb9d344e` | `benchweave evidence runs --dest docs/evidence/poc` |
| `runs/run-018.json` | generated | `afc2a751616de08f69f2e26c37f5c98636f21302f77bf53143f144038c544f50` | `benchweave evidence runs --dest docs/evidence/poc` |
| `runs/run-019.json` | generated | `92d7c8a540da5b37ab8e472964c8a828cce4ac8f2f8c51343ffc5e45ac059bbe` | `benchweave evidence runs --dest docs/evidence/poc` |
| `runs/run-020.json` | generated | `b50ff00de5f0ff6ae4628d427499da7735db46b47ae64c3da2968461b487849a` | `benchweave evidence runs --dest docs/evidence/poc` |
| `runs/run-021.json` | generated | `72512d79b54c12e822d9fdd974c5ce19baefa2a8a10b681665de52b61193a706` | `benchweave evidence runs --dest docs/evidence/poc` |
| `runs/run-022.json` | generated | `03d03a63459ac53d1c8c86e05402a5e8d9f248e7243e890fe8550ac418b3c17b` | `benchweave evidence runs --dest docs/evidence/poc` |
| `runs/run-023.json` | generated | `7dde55a8edd8bce863e4e5248eaadea6669171fd79a419f4775723de9ebdf0b2` | `benchweave evidence runs --dest docs/evidence/poc` |
| `runs/run-024.json` | generated | `7eb58e52de23158b3c333fe7e90503da70fabc414078b0c8cfe2cb566c21075e` | `benchweave evidence runs --dest docs/evidence/poc` |
| `runs/run-025.json` | generated | `9ea32c7ad284437f65fe7d8929584ab67f8a2ae89f25c1e3202ec534b80d2b46` | `benchweave evidence runs --dest docs/evidence/poc` |
| `runs/run-026.json` | generated | `6d8b637db15253a262b63ac9adcc4d8d95b9f09536d631cc6b047d76c26f05db` | `benchweave evidence runs --dest docs/evidence/poc` |
| `runs/run-027.json` | generated | `38442f07ffb9c26d12d9ddc6af18b432097fa790cf7421ca9400bca4ab7a2d67` | `benchweave evidence runs --dest docs/evidence/poc` |
| `runs/run-028.json` | generated | `5cff957f07ca92c328abed77047a159407bc9fbfe51bc547ed5dccd6c56ce555` | `benchweave evidence runs --dest docs/evidence/poc` |
| `runs/run-029.json` | generated | `74582da9167c88a02828eb2bb505d3bde1f311a1eccf5897fe249883c4e7ceab` | `benchweave evidence runs --dest docs/evidence/poc` |
| `runs/run-030.json` | generated | `69f117c773663d07fa0f5f6fb59506d613129bf56dc0d481a563cb1433ae73dd` | `benchweave evidence runs --dest docs/evidence/poc` |
| `runs/run-031.json` | generated | `993d61769b8a05d6359a598c870618dca119f8ed07313735ca0a5856c4b3eff0` | `benchweave evidence runs --dest docs/evidence/poc` |
| `runs/run-032.json` | generated | `d0e528300d68ce48408bd11c53edda6a0a0f97bdda6bbfce6e09e4d9826fe526` | `benchweave evidence runs --dest docs/evidence/poc` |
| `runs/run-033.json` | generated | `963c538461b10c851577e91fbfa4a30b91de9c6ed2bb39b905574648ff4cb1e2` | `benchweave evidence runs --dest docs/evidence/poc` |
| `runs/run-034.json` | generated | `b40ed1b6d57fc260f09e5e3266b25c2d867bbcfd8c305744dabe7f17dc6631d3` | `benchweave evidence runs --dest docs/evidence/poc` |
| `runs/run-035.json` | generated | `369084ab9677cac73892309c68b26375684eb156d9a54e88c59fe0f8b8dc1292` | `benchweave evidence runs --dest docs/evidence/poc` |
| `runs/run-036.json` | generated | `ec6208d92d69fd9f3310822e5e9c74e24bea3c81a0f7383f28ecabc4efc8b547` | `benchweave evidence runs --dest docs/evidence/poc` |
| `runs/run-037.json` | generated | `3de3cbf7a809f6759642ae583292debb54af5d6e067f934b4056021162fcdce0` | `benchweave evidence runs --dest docs/evidence/poc` |
| `runs/run-038.json` | generated | `623c1c9efbcec5f426c04546f0d0a72d57bb0ae16ffe590dea293888d59b2a2b` | `benchweave evidence runs --dest docs/evidence/poc` |
| `runs/run-039.json` | generated | `9de903d1c3281b9ca00a16d8154821c01dd8489931d83ab9a3eda5f93652c91e` | `benchweave evidence runs --dest docs/evidence/poc` |
| `runs/run-040.json` | generated | `e8c588b72aaa307234dd9034d1ab956ef88f821ac7d415ed27c519fb27f44043` | `benchweave evidence runs --dest docs/evidence/poc` |
| `runs/run-041.json` | generated | `6c297dceb96000a9d1e33bb27ef1b97b920fc2602bc1345b298ad0344abfd86b` | `benchweave evidence runs --dest docs/evidence/poc` |
| `runs/run-042.json` | generated | `5acaa32fe826508d8ba6c6a8039a82474fd4e56e17339cf6481660399eadb128` | `benchweave evidence runs --dest docs/evidence/poc` |
| `runs/run-043.json` | generated | `96f27b603e9cb591850dc3e0297a998001c0e2504b6d8b1124825dab0f0a0c0a` | `benchweave evidence runs --dest docs/evidence/poc` |
| `runs/run-044.json` | generated | `37c774d08bee9325469814e5b2847f7cb93b3defc135d1e48110afe3d7479781` | `benchweave evidence runs --dest docs/evidence/poc` |
| `runs/run-045.json` | generated | `8b16f90ff517c684c0e43548e80b1663c3f184d2ae30cac9f73a3c1b40053b07` | `benchweave evidence runs --dest docs/evidence/poc` |
| `runs/run-046.json` | generated | `6727bb8d6fa24aef0b070e7b7f2dfd13272a547752a9fcfaec209bfbafb8c2e4` | `benchweave evidence runs --dest docs/evidence/poc` |
| `runs/run-047.json` | generated | `01c8b21af1a03f8190dd04036bc77d51a840890ef9170833e752f47f97ef3e56` | `benchweave evidence runs --dest docs/evidence/poc` |
| `runs/run-048.json` | generated | `fb6c7f72a17803758fefb13728de15c7cca58ccbe0cef5a025bd336635ae9cc6` | `benchweave evidence runs --dest docs/evidence/poc` |
| `runs/run-049.json` | generated | `661a7cf5a7ecb10eb4bb328b4f965abc9ae24c4b2e5218d53ee5044422274890` | `benchweave evidence runs --dest docs/evidence/poc` |
| `runs/run-050.json` | generated | `2649393b8e232f125a35f457f319842dda06aea464587e89e8842078449d7a87` | `benchweave evidence runs --dest docs/evidence/poc` |
| `runs/run-051.json` | generated | `3e8bb927e471dd705c9b39a524fc1fbbf35f926c6938c2ede508c9110190a635` | `benchweave evidence runs --dest docs/evidence/poc` |
| `runs/run-052.json` | generated | `027646cf7b0dc50542214e2128ad009d991e017d6207c2e37a0b7664794b3f5e` | `benchweave evidence runs --dest docs/evidence/poc` |
| `runs/run-053.json` | generated | `8127e76b64b34d9a0b0baaf446566b406eb47bd25353d9294e1145fdf09a0364` | `benchweave evidence runs --dest docs/evidence/poc` |
| `runs/run-054.json` | generated | `73ff5f5b9b86e891f5dc5bc81a42c884e9191b07d7d1e6ce241013cc3bcf30c3` | `benchweave evidence runs --dest docs/evidence/poc` |
| `runs/run-055.json` | generated | `7f0a971a754d2fe7250355fec438eb5deff8e9406f3359965b3c1eb78b616bfd` | `benchweave evidence runs --dest docs/evidence/poc` |
| `runs/run-056.json` | generated | `115a832b17326322ce5011a28711a9ef0f84b6b1cd1630042244cdcf79f0c0ad` | `benchweave evidence runs --dest docs/evidence/poc` |
| `runs/run-057.json` | generated | `f91ca6a8ddbe77fcd3dd8bf60d277f45c21234cf264b7dcd343be124d1fc5a4c` | `benchweave evidence runs --dest docs/evidence/poc` |
| `runs/run-058.json` | generated | `9166b3e2f038d972bdd432b4e9fe92898e5866f61d7402d30a857f8670104d5f` | `benchweave evidence runs --dest docs/evidence/poc` |
| `runs/run-059.json` | generated | `b044dbd4726eea90f05c34f813dfea483895aaa90cf4f980fa45d8671fb881e7` | `benchweave evidence runs --dest docs/evidence/poc` |
| `runs/run-060.json` | generated | `6294e804cee800324b3d291d555424200d665e5f3ca1174e3bde5573ea5cc7d5` | `benchweave evidence runs --dest docs/evidence/poc` |
| `runs/run-061.json` | generated | `104c2022922603f4e35114e23f2bbe7bb3a03f64c500b9745af114660a050f1a` | `benchweave evidence runs --dest docs/evidence/poc` |
| `runs/run-062.json` | generated | `eb66a95426ed56bbf847a637823856b1dbe38f70b4907b3972ff083edf8819e8` | `benchweave evidence runs --dest docs/evidence/poc` |
| `runs/run-063.json` | generated | `1ab41f4e31a8ba59101fe30e2f6414e615f330d23690ca89ad8d6c28cc6a83ab` | `benchweave evidence runs --dest docs/evidence/poc` |
| `runs/run-064.json` | generated | `4a50db1aef6ca16fa08a9052059c40e4f137bc2a7e4c97e9b129c29c9c5a54ea` | `benchweave evidence runs --dest docs/evidence/poc` |
| `runs/run-065.json` | generated | `9c5372ce4c12aeb7259b7cfedaf65ea72195db59779fa234583270fbeea6e5d2` | `benchweave evidence runs --dest docs/evidence/poc` |
| `runs/run-066.json` | generated | `9fc0bde6a55b0a5c6bbbde710a4ab139308c3ac79fda94db7aa1cf2f1fa4d9a8` | `benchweave evidence runs --dest docs/evidence/poc` |
| `runs/run-067.json` | generated | `bb82b4371f6942b0fb79fc7235172e8b23bbca7ed2964692be9093b1ec5e3716` | `benchweave evidence runs --dest docs/evidence/poc` |
| `runs/run-068.json` | generated | `2e6696dff86d52a9f8ca414271215af272c4ed8ee6c604e3f51104062fe5c4ae` | `benchweave evidence runs --dest docs/evidence/poc` |
| `runs/run-069.json` | generated | `3f92bdf04ab0d7e51613fa150f6d4511c2ac0a85204149abbb43477a7cb0d0f9` | `benchweave evidence runs --dest docs/evidence/poc` |
| `runs/run-070.json` | generated | `bcf8dc6f1e10e821c5588075fde2c719d0787481f40e58dc7b5d0ac81ec18e62` | `benchweave evidence runs --dest docs/evidence/poc` |
| `runs/run-071.json` | generated | `3b73319276250b8a6f543e12d00e9f9c564a9e5b8975306c42097063f0947aeb` | `benchweave evidence runs --dest docs/evidence/poc` |
| `runs/run-072.json` | generated | `0ffc6bf2f9acc15e674015632648af53952e152d64c3bed4736cd9ed405c4745` | `benchweave evidence runs --dest docs/evidence/poc` |
| `runs/run-073.json` | generated | `4eecd1d20182b3a492b46a76ff568cc6cce4d0e0147794ef8a2a1d1151c8c209` | `benchweave evidence runs --dest docs/evidence/poc` |
| `runs/run-074.json` | generated | `8ac148cf80f7322187d59abb9ced84d09239ba3018847ab15c30e1a462ff5694` | `benchweave evidence runs --dest docs/evidence/poc` |
| `runs/run-075.json` | generated | `7c3ea99def436533f216d730dab82e2351d2b20e2b047af6c3c5a49251451260` | `benchweave evidence runs --dest docs/evidence/poc` |
| `runs/run-076.json` | generated | `06afcd8414a4fc60b01a5976abd05d16eb4b4770cd696e76e1ad8a38493d377c` | `benchweave evidence runs --dest docs/evidence/poc` |
| `runs/run-077.json` | generated | `b791ababde13740649d318d892060bb66b757a2f9fbfd138eb61f616dc91fc3b` | `benchweave evidence runs --dest docs/evidence/poc` |
| `runs/run-078.json` | generated | `331da173721f1aa7131049e87c9e9081e78db9dddc60993ad1bd8b47876affb9` | `benchweave evidence runs --dest docs/evidence/poc` |
| `runs/run-079.json` | generated | `60b8af5271a8b80efdd792aa45f058c7367e450f6101e59a2b139a5b80137835` | `benchweave evidence runs --dest docs/evidence/poc` |
| `runs/run-080.json` | generated | `f8c1222010553ab09b9fa434875351fbbc9c08cac3be84f32597bd1e94d4bf0c` | `benchweave evidence runs --dest docs/evidence/poc` |
| `runs/run-081.json` | generated | `5d21cd2cb5c4ca985077c16238249f3f551e74fa46a1e9c0eec889178bf317f1` | `benchweave evidence runs --dest docs/evidence/poc` |
| `runs/run-082.json` | generated | `b646a6fd5169402bb9d0914fc316aa80dbb445c65411d0a23d198d08efa102df` | `benchweave evidence runs --dest docs/evidence/poc` |
| `runs/run-083.json` | generated | `8c37620c6ae12e564801f23085458aa02b00604a9403b1e009e890cba2b24266` | `benchweave evidence runs --dest docs/evidence/poc` |
| `runs/run-084.json` | generated | `ff7d06e58b3b21433603fb2a8aa20d82c542f49569a09a04d5e00d4ab72abe8b` | `benchweave evidence runs --dest docs/evidence/poc` |
| `runs/run-085.json` | generated | `c819180f7d369db7cfc1135c3a08ecf4f9cd190b332286f982685486391b0c8a` | `benchweave evidence runs --dest docs/evidence/poc` |
| `runs/run-086.json` | generated | `a625e99128375e1a7f442a035c5322199f4c465acfb5007ab6585baf29ac1c2d` | `benchweave evidence runs --dest docs/evidence/poc` |
| `runs/run-087.json` | generated | `d22af5ecbbc7a70e8d097c6a93a3f7b6ade60e3d9c2b12c033ca7e6e68a3d9aa` | `benchweave evidence runs --dest docs/evidence/poc` |
| `runs/run-088.json` | generated | `c007066d9f0861b3b057dd1b7235d498ed57fc3944d6883f9bbdd23de1a8be6a` | `benchweave evidence runs --dest docs/evidence/poc` |
| `runs/run-089.json` | generated | `e34c07dee34667f04d4c60665e75a914cd9dee1a911738f3009524c6d31a2dbf` | `benchweave evidence runs --dest docs/evidence/poc` |
| `runs/run-090.json` | generated | `77f412ba8a2b281ce0d0000e29a02213807d67cc63c6df32cc3508207d67e4e9` | `benchweave evidence runs --dest docs/evidence/poc` |
| `runs/run-091.json` | generated | `570315b809f237518d782871e0a1e0a690cd21330a6cf8ac462b29062ed0d610` | `benchweave evidence runs --dest docs/evidence/poc` |
| `runs/run-092.json` | generated | `5af673f9b742b7692f9a35c8f7476bd5986c78f43b3912b46d12a5854314114d` | `benchweave evidence runs --dest docs/evidence/poc` |
| `runs/run-093.json` | generated | `f090ac069b72821ae89c76a084a4633b4f377127068d7677f705740e2dd21969` | `benchweave evidence runs --dest docs/evidence/poc` |
| `runs/run-094.json` | generated | `145006029313a454d78833b37069743d94538f25afd41cf447a6fca0baf8506a` | `benchweave evidence runs --dest docs/evidence/poc` |
| `runs/run-095.json` | generated | `637c22097d48bb7b9eb2b4e8cecb9c22df2f2186c5abf52f16e8e598d4e492f2` | `benchweave evidence runs --dest docs/evidence/poc` |
| `runs/run-096.json` | generated | `1fcf6799903bd96b589b54f20c17e7088936b2c2dccab42c2df280aab58bb7a8` | `benchweave evidence runs --dest docs/evidence/poc` |
| `runs/run-097.json` | generated | `17e585d3cabbed2846ff155032faac0b9210cdd6df551eaac8e275cfc979f9b2` | `benchweave evidence runs --dest docs/evidence/poc` |
| `runs/run-098.json` | generated | `f1501e8b764fbcc888ba243967b2b9daa3ff69ac2aa3e3a36bfdfc1765aefa7a` | `benchweave evidence runs --dest docs/evidence/poc` |
| `runs/run-099.json` | generated | `773eb4b815bdb8f6d7255a38c778ecd2cf9ec65703c5882a83f191917e3f173c` | `benchweave evidence runs --dest docs/evidence/poc` |
| `runs/run-100.json` | generated | `3076ae012a1a5221af630563a138b517ddabbdee98f2a229831e83548e335e58` | `benchweave evidence runs --dest docs/evidence/poc` |
| `runs/summary.json` | generated | `d89c0df2965f01cf29fa2c950db890a5f2e09361ffd2f5579a371c491f11c145` | `benchweave evidence runs --dest docs/evidence/poc` |
| `timed-demos/leg-1-clean-demo.md` | record | `920479fc368fc73c3127a858caa118bccdb022094638cfc503850c4057dbe4ae` | record — digest-bound, never regenerated |
| `timed-demos/leg-2-second-install-reuse.md` | record | `d0d996b8631bba3d4067117445e86187ee6359d3b11f67bf7345225e95d3d5c7` | record — digest-bound, never regenerated |
| `timing/prd-load.json` | generated | `a2b3d00d896b0cb8a6fa688fb675f1a89dd48b15e1b01b59af7cd80c4adc6cc4` | `benchweave evidence timing --dest docs/evidence/poc` |
| `timing/stress-16.json` | generated | `d2f3c88da18821701293020df1c044794709d54ce08a37484850c4c571e1d1f6` | `benchweave evidence timing --dest docs/evidence/poc` |
