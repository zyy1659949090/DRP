python -u build_model.py -p @descs/itml_5k_InfoGain_nonzero_thesis.dsc -trs geoffrey_split_for_thesis_0 -tes geoffrey_split_for_thesis_1 -v -mt SVM_PUK_basic -d "geoffrey thesis SVM itml_5k_InfoGain_nonzero" &> SVM_basic_itml_5k_InfoGain_nonzero_thesis.out &
python -u build_model.py -p @descs/itml_5k_InfoGain_nonzero_thesis.dsc -trs geoffrey_split_for_thesis_0 -tes geoffrey_split_for_thesis_1 -v -mt SVM_PUK_BCR -d "geoffrey thesis BCR SVM itml_5k_InfoGain_nonzero" &> SVM_BCR_itml_5k_InfoGain_nonzero_thesis.out &
python -u build_model.py -p @descs/itml_5k_InfoGain_nonzero_thesis.dsc -trs geoffrey_split_for_thesis_0 -tes geoffrey_split_for_thesis_1 -v -mt KNN -d "geoffrey thesis BCR SVM itml_5k_InfoGain_nonzero" &> KNN_itml_5k_InfoGain_nonzero_thesis.out &
python -u build_model.py -p @descs/itml_5k_InfoGain_nonzero_thesis.dsc -trs geoffrey_split_for_thesis_0 -tes geoffrey_split_for_thesis_1 -v -mt J48 -d "geoffrey thesis BCR SVM itml_5k_InfoGain_nonzero" &> J48_itml_5k_InfoGain_nonzero_thesis.out &
python -u build_model.py -p @descs/itml_5k_InfoGain_nonzero_thesis.dsc -trs geoffrey_split_for_thesis_0 -tes geoffrey_split_for_thesis_1 -v -mt NaiveBayes -d "geoffrey thesis BCR SVM itml_5k_InfoGain_nonzero" &> NB_itml_5k_InfoGain_nonzero_thesis.out &
